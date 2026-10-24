# 第 6 章实验报告

## 配置与完成清单

- 验证日期：2026-10-24；Linux，Python 3.11.16；在 `/tmp` 隔离 venv 运行。
- 模型：`offline-extractive-and-p5-plan-fixture`，确定性规则夹具，无温度、网络模型调用或 provider usage。问题回答摘录真实工具返回，计划复用 P5 离线模型；没有给模型传评分标签。
- 依赖：LangGraph 1.2.16、SQLite checkpointer 3.1.2、httpx 0.28.1、OpenTelemetry SDK/API 1.45.1、LangSmith 0.14.12。完整可重建依赖在 `requirements.lock.txt`。
- P6-01～05 已实现；真实 DeepSeek 适配复用公共模块，协议和 usage 解析有无网络测试，但真实 API 调用未验证。
- 数据：30 道开发题，知识/比较/记忆/故障/计划各 6；独立 holdout 6 题。标签从仓库段落和明确业务规则编写，运行前固定；没有为通过测试修改标准答案。`annotation_status=complete` 表示字段完整，不宣称有人完成模型输出审查。
- 预算：每题模型最多 8 次、循环最多 8 轮、工具最多 24 次、整题 30 秒；上下文估算上限 24,000，保留输出 2,000。失败和重试都计数。
- baseline 是关闭检索重试和写入读回/重试的故障对照；其余配置、模型、输入和评分器与 fixed 一致。它不是对 P5 原始正确率的测量。

## 对照结果

以下为**自动机械/抽取式检查通过率**。独立人工语义审查尚未完成，尤其比较题的离线回答只是摘录对照，不能把下表当作真实模型的完整答案正确率。

| 方案 | 单次通过 | 三次全通过 | 平均模型调用 | 平均工具调用 | p50 秒 | p95 秒 | token usage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 开发 baseline | 75/90 (83.33%) | 83.33% | 1.567 | 2.367 | 0.073518 | 0.154486 | unavailable |
| 开发 fixed | 90/90 (100.00%) | 100.00% | 1.633 | 3.133 | 0.125917 | 0.154362 | unavailable |
| 独立 holdout fixed | 6/6 (100.00%) | 不适用（每题一次） | 1.667 | 3.167 | 0.079136 | 0.164019 | unavailable |

开发集 baseline 的 25/30 题三次均通过，fixed 为 30/30；这是作业定义的三次重复指标，不是完整 τ-bench pass^k，也不是 pass@k。确定性夹具重复三次不能说明随机模型的稳定性。

有引用运行的来源/观察/摘录检查均为 100%；分母分别是 baseline 78、fixed 87、holdout 5，缺证题不计入引用分母。这个指标同样不代替语义正确性。

fixed 开发集核心规则：未经确认写入 0/51；重复操作违规 0/6；引用伪造 0/90；新偏好未生效 0/15。另检查声称保存成功的 42 次结果，全部与真实数据库内容一致。baseline 有 6 次假保存被抓到，包含已有 ID 但内容没更新的情况。

## 两个主要失败原因与修复

1. **把临时检索错误当作终局。** `fault-01`/`fault-02` 首次查询抛 OSError；baseline 未生成候选计划，数据库保持空，预期终态失败。fixed 在同一检索阶段最多重试一次，真实查询返回证据后继续。见 [baseline 轨迹](evidence/development/development/baseline/fault-01/trial-1/trace.jsonl) 和 [fixed 轨迹](evidence/development/development/fixed/fault-01/trial-1/trace.jsonl)。连续失败三次的回归测试证明不会无限重试。
2. **把写入响应当作持久化事实。** `fault-03` 注入返回 task ID 但不写磁盘，baseline 的回复标为 completed，数据库却为空，final_state/truthful_save 判失败；`fault-04` 更新旧 ID 也能暴露这个错误。fixed 读取真实任务内容，缺失/不符时使用原 operation_id 重试。`fault-05` 落盘后丢失响应也复用该 ID，所以最终只有一条任务和一个操作记录。见 [假保存 baseline](evidence/development/development/baseline/fault-03/trial-1/trace.jsonl)、[读回修复](evidence/development/development/fixed/fault-03/trial-1/trace.jsonl)、[丢失响应后的重试](evidence/development/development/fixed/fault-05/trial-1/trace.jsonl)。

开发中还发现 `Short-term-memory` 的弱词匹配会引入只含 memory 的段落。保持原标签不变，两组统一在 P1 排序结果中保留最高分，避免计划主题漂移。这是适配层共同的检索处理，不计入上述恢复对照差异。

## Holdout 与实现冻结

holdout 在开发集、24 项回归测试通过后才执行一次，没有拿其结果继续调参。两次正式运行记录的实现摘要相同：

`a36ca74e61eb3510c4514cb35dabccf43dba1a7f3b5c333e84e0f4e8fc8cf6dc`

6 题包括未使用过的知识题、跨资料比较、50→18 分钟档案更新、查询失败与写入响应丢失组合、已有任务更新后重复恢复，以及不同主题的缺证问题。6/6 通过机械检查；不合并到开发集分母。结果见 [holdout 原始数据](evidence/holdout/results.jsonl)。

## 可观测性与验收证据

- [开发集 180 条原始结果](evidence/development/results.jsonl)、[汇总](evidence/development/summary.json)、[运行清单](evidence/development/manifest.json)。结果包含 actual 和从磁盘读取的 final_state，各行 trace_path 相对于本套 evidence 目录。
- [开发集 OTel spans](evidence/development/spans.jsonl)：180 个 task 根 span、783 个模型/工具子 span；程序验证每个子 span 的 parent_id 存在且 trace_id 一致。错误工具 span 含 ERROR 状态和异常事件。
- [holdout 汇总](evidence/holdout/summary.json)、[运行清单](evidence/holdout/manifest.json) 与所有逐题 trace 单独保存。
- [24 项回归测试输出](evidence/unit-tests.txt)；`pip check` 与 `git diff --check` 通过。公共 CLI 的 P6 status/demo/run、P5 status 和 P1 demo 已检查。
- `human_review.json` 已生成，所有人工签名及 semantic_correct 保持空值。`review.py` 在审查未完成时保持 pending，拒绝输出正式语义成功率。
- LangSmith：SDK 集成已实现，模拟客户端测试验证根/子运行与读回确认流程；本机无 LANGSMITH_API_KEY，实际服务上传**未验证**，正式 manifest 显示 disabled。没有伪造线上 trace 链接。
- DeepSeek：本机无 DEEPSEEK_API_KEY，实际模型能力、成本及供应商 token usage **未验证**。没有用离线次数冒充真实调用。

复现命令（仓库根目录、已安装锁定依赖的 Python 3.11 环境）：

```sh
python -m unittest p6_evaluation.practice.test_evaluation -v
python practice.py 6 run --provider offline
python practice.py 6 run --provider offline --input p6_evaluation/practice/data/holdout-input.json
```

## 判断与剩余边界

评测器确实能区分“回复好看”与“业务状态正确”，并定位失败阶段。一次有限检索重试和写入读回/幂等重试修复了注入故障，平均工具调用由 2.367 增至 3.133；本地夹具的毫秒耗时不能外推至线上模型。

本次交付完成可运行的评测机制、数据、恢复对照和本地追踪。完整课程的真实模型抽样、独立人工语义审查、LangSmith 线上 trace 仍需要外部凭据或评审者；不声称这些验收已完成，也不声称复现 τ-bench。
