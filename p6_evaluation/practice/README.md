# 第 6 章：可重复评测与可观测性

本章提供 30 题开发集（五类各六题）、6 题独立 holdout、真实磁盘状态判分、OTel 父子 span、可选 LangSmith 样例上传，以及人工语义复核入口。模型无法读取评分标签。

## 安装与运行

使用仓库约定的 Python 3.11 `agent-learn` 环境。依赖仅安装到该环境；本次 Linux 验证使用 `/tmp` 下的隔离 venv，未更改已有 Conda 环境。

```powershell
conda activate agent-learn
python -m pip install -r p6_evaluation/practice/requirements.lock.txt
python practice.py 6 run --provider offline
```

也可使用原有 Windows 入口：

```powershell
.\scripts\practice.ps1 6 run --provider offline
```

一条命令运行 baseline/fixed 各 30 × 3 次，生成独立 `artifacts/evaluation-<uuid>/`。终端输出每组汇总与路径。`status` 仅列任务清单，`demo` 仍然只检查基础设施。

开发完成并冻结实现后，单独运行 holdout，每题一次，不参与 baseline 调试：

```powershell
python practice.py 6 run --provider offline --input p6_evaluation/practice/data/holdout-input.json
```

禁止把两套数据的分母合并。每个 trial 都有新目录、新检查点、新模型计数和初始数据库；同一个 trial 内确认与恢复会重新打开 P5 的 SQLite 检查点。

## 实现与复用

| 任务 | 实现 |
| --- | --- |
| P6-01 | `solution.reset_environment`：深拷贝初始数据库，拒绝复用已有 trial 目录 |
| P6-02 | `solution.evaluate_case`：结构、事实、引用摘录、动作约束、规则、磁盘终态 |
| P6-03 | `solution.summarize`：单次成功率、三次全成功比例、调用均值、线性插值 p50/p95 |
| P6-04 | `observability.py`：真正的 OTel SDK/exporter；可选一棵 LangSmith task/model/tool trace |
| P6-05 | `solution.run`：分套运行、逐条写原始结果、配置/数据/代码摘要、复核模板 |

`agent.py` 直接复用 P1 检索、P2 幂等写入、P3 档案更新、P5 LangGraph 状态机与 SQLite 恢复。知识题使用带真实工具反馈的模型循环；计划题通过 P5 的确认中断节点。跨会话档案从磁盘重开读取，不把旧 Python 对象当新会话数据。没有模拟向真实用户发送消息。

`offline.py` 是明确的规则夹具：知识题摘录实际检索段落，计划题复用 P5 离线生成器。它只收到问题、检索提示和工具结果，不接触 expected_*。其成功率只能证明评测和工作流机制，不能证明真实 LLM 自主选工具、理解比较题或随机采样可靠性。

`baseline` 与 `fixed` 使用同一模型、数据、提示和预算。baseline 是故意移除恢复保护的实验对照，并不代表 P5 的全部原始行为。fixed 增加：检索暂时失败重试一次；写入读回校验与稳定 operation_id 重试一次。故障包括查询暂时失败、假成功未落盘、落盘后响应丢失。规划检索在两组中都筛选最高相关分数，避免仅匹配一个通用词的弱相关段落进入计划。

## 真实模型

```powershell
$env:DEEPSEEK_API_KEY = "在本机设置，不要提交"
python practice.py 6 run --provider deepseek
```

复用公共 `DeepSeekAdapter`：原生 tool_call_id 与真实工具结果对应，使用可取消的异步 HTTP，记录供应商返回的 usage。每个 trial 单独创建适配器，失败请求也消耗预算。该命令会进行完整开发集调用；可在 Python 中调用 `_trial` 做少量冒烟验证。没有密钥时 CLI 明确退出，不把离线结果标为线上结果。

模型调用、工具调用、轮数和整题超时分别有预算；问答按 UTF-8 字节保守限制输入，P5 保留自身字符估算。两者都是上下文上限估算，不是实际 token usage。离线 usage 为 unavailable，而非虚构的 0 token 消耗。

## 判分与人工复核

参见 [RUBRIC.md](RUBRIC.md)。`summary.json` 是机械/抽取式检查的结果。题目 rubric 还要求人核对自由文本语义，尤其比较题是否真正说明差异；这里没有把 AI 作者或自动测试伪装成人工评审。

每次运行生成 `human_review.json`。人工逐题阅读 answer、rubric 和 trace 后，填写 `reviewer`、布尔值 `semantic_correct`、`notes`，再执行：

```powershell
python -m p6_evaluation.practice.review p6_evaluation/practice/artifacts/evaluation-实际ID
```

未复核行保留 pending；未全部完成时不会给出正式语义成功率。人工只能补充引用与结论的语义支持判断，不能覆盖数据库终态、必需事实、禁止动作等失败。

## 追踪与产物

- `results.jsonl`：逐题原始 actual、磁盘终态、checks、规则、调用数、usage、耗时、trace_id 和相对 trace_path。
- `spans.jsonl`：OTel JSON，task 是根，模型和工具为子 span；异常包含 error status/events。
- 每个 trial 的 `trace.jsonl`：实际参数、观察、故障、确认、重试、恢复；`study_tasks.json`、`profiles.json`、`checkpoints.sqlite` 是隔离的真实存储。
- `manifest.json`：Python/依赖版本、预算、开发/holdout 区分、数据/语料/实现 SHA-256。
- `summary.json`、`human_review.json`：自动汇总与独立人工复核。

LangSmith 默认为关闭。需要上传一条样例时，在输入 JSON 中加入 `"langsmith_sample": true`，并设置 `LANGSMITH_API_KEY`、可选 `LANGSMITH_PROJECT`。只上传第一题及其模型/工具子运行，含实际输入输出。SDK 写入并读回 run 后才标为 verified；缺密钥为 not_configured，服务失败为 upload_failed，本地评测继续。未配置的服务不冒充真实线上验证。

## 回归测试与证据

```powershell
python -m unittest p6_evaluation.practice.test_evaluation -v
```

测试覆盖评分防误判、假保存、假更新、丢失响应后的幂等重试、独立环境、确认/拒绝、检查点恢复、档案隔离、预算/取消、OTel 父子关系、LangSmith SDK 调用与人工复核入口。测试不执行 holdout。结果与限制见 [report.md](report.md)，本次运行的可审查数据保存在 `evidence/`。

参考：[OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/instrumentation/)、[LangSmith RunTree](https://reference.langchain.com/python/langsmith/run_trees/RunTree)。
