# P4：三个角色商量一次学习讨论

目标：主持人懂 ReAct，资料员懂 Toolformer，质疑者懂 MemGPT。
他们交换信息、安排议程、修正错误，最后形成各自的反思和下一版安排。

**先读 `solution.py` 的 `collaborate()`。** 它按 1–7 标了完整顺序。
不用先理解所有 AutoGen 细节，也没有插件注册表、配置继承或额外环境变量。

## 运行

在仓库根目录、已有 `agent-learn` Conda 环境中安装：

```powershell
conda activate agent-learn
python -m pip install -r p4_multi_agent_cowork/practice/requirements.txt
```

`config.json` 的 `provider` 当前为 `offline`，可以改成 `deepseek`。
优先级：`--provider` 参数 > 调试器已有的 `MODEL_PROVIDER` > `config.json`。
启动时打印 `P4 provider: ...`，可确认实际选择。调试器里的 `scripted` 对应离线规则模型。
没有参数和环境变量覆盖时，下面命令按 config 运行：

```powershell
.\scripts\practice.ps1 4 run
.\scripts\practice.ps1 4 run --evaluate
```

真实模型复用根目录 `api-key.txt` 中的 DeepSeek 密钥（不要提交密钥）：

```powershell
.\scripts\practice.ps1 4 run --provider deepseek
.\scripts\practice.ps1 4 run --evaluate --provider deepseek
```

真实运行会向 DeepSeek 发送模拟角色档案、三段学习笔记和讨论消息，并产生费用。
模型写死为 `deepseek-chat`，每次回答最多 900 output tokens。
每组共用 18 次调用上限，修订最多 6 轮，正常响应等待上限 30 秒。
调整这些数值只需看 `config.json` 与 `models.py:make_model`。

也可以直接使用已激活环境的 `python practice.py 4 run`。
`demo` 仍是公共脚手架的演示，不是本章算法；看本章请用 `run`。

## 代码怎么读

| 文件/函数 | 做什么 |
| --- | --- |
| `data/profiles.json` | 三人的身份、知识和可用时间，日期是固定实验数据 |
| `contracts.py` | 消息和计划的数据结构 |
| `planning.py:validate_plan` | 检查时间交集、议程时长、分工、主题、证据 |
| `solution.py:collaborate` | 整个流程，按顺序读即可 |
| `solution.py:StudyAgent` | 一个角色收到消息时：记录观察，或调用模型 |
| `solution.py:build_team` | 向 AutoGen 注册三个独立角色 |
| `solution.py:route_message` | 核对消息地址，投递，等待，超时返回 |
| `solution.py:reflect` | 调用模型归纳经验，检查观察来源 ID |
| `offline.py` | 可读的规则模型，只验证流程，不模拟真实推理效果 |
| `models.py` | 统一选择 provider、创建模型 |
| `experiment.py` | 读取八个场景、做三组对照、保存结果 |
| `test_practice.py` | 九个测试，覆盖 provider 选择、通信隔离、故障修复、预算等 |

调用路径：

```text
practice.py → experiment.launch → solution.run → collaborate
                                                   ↓
                         send → route_message → AutoGen → StudyAgent.receive
                                                             ↓
                                                        model.respond
```

依赖方向：入口 `experiment` → 流程 `solution` → 模型 `models/offline` 与规则 `planning`，没有反向导入入口。

`async/await` 只用于等待 AutoGen 消息。这里没有同时运行多个模型的并发逻辑。
同步 HTTP 被放到线程中；HTTP 超时由已有模型适配器处理，不能把线程取消误认为网络请求已撤回。

## 一次运行发生什么

1. 主持人只用自己的资料先提案，保留 `before_communication`。
2. 确认其他角色在线。缺席测试会实际等待并触发超时，不只是设置一个缺席标签。
3. 角色交换档案和证据，再提案，保留 `after_communication`。
4. 测试需要时注入时间冲突或伪造引用。
5. 代码检查计划；质疑者评论；把检查结果传回主持人，重新生成。代码检查通过或耗尽轮数就停止。质疑者的评论作为后续输入，不独立决定通过与否。
6. 有反思组每个在场角色生成一条 `inference + source_ids + next_action`。
7. 主持人在相同约束下再生成 `next_plan`。这是后续方案，不是自动约到下个星期。

真实模型可能输出错误 JSON、漏掉反思来源，或生成不合约束的下一版计划。
这三处各允许一次反馈修订，全部仍受 18 次总调用上限约束，不循环到“碰巧成功”。

三个模式：

- `single`：所有模型决策都由主持人执行，其他角色只提供固定档案。
- `multi`：主持人生成，质疑者评议，不做反思。
- `multi_reflection`：再加入各角色独立反思，主持人的反思进入下一次方案输入。

可修改 `data/input.json` 的 `mode`、`fault`，然后运行。支持的故障为
`time_conflict`、`forged_reference`、`absent` 或 `null`。
要换时间，修改角色档案，或在输入的 `profiles` 字段提供完整三人列表。
角色 ID 固定为 `host/researcher/critic`；主题固定为三个课程主题，刻意不做通用框架。

## 看哪些结果

- `artifacts/last_result.json`：单次完整结果，包括各角色独立记忆。
- `artifacts/run.jsonl`：每条消息、模型输入输出、校验与实际 usage。
- `artifacts/offline/evaluation.json`：离线 24 组结果。
- `artifacts/deepseek/evaluation.json`：真实模型 24 组结果。
- `artifacts/<provider>/<场景>/<模式>/`：逐组结果与 trace。
- `report.md`：实验说明与历史结果摘要。

状态区分 `completed`（完整可用）、`degraded`（缺席，只有部分计划）、
`infeasible`（无共同时间）、`invalid_plan`、`invalid_next_plan`、
`budget_exhausted` 和 `failed`。不把缺席/不可行算作完整计划成功。

## 这份实现刻意保持简单的地方

- AutoGen Core 真实管理角色和消息；讨论顺序是自己写的固定 workflow。
  没有宣称让模型自主选择收件人。AutoGen 已归档，这里锁版本用于理解课程。
- 资料员提供固定笔记片段，`tool_calls=0` 是真实值；没有假装模型执行了检索工具。
  `data/corpus.jsonl` 来自本地 P1–P3 笔记，保留源文件和行号，不修改公共旧语料。
- 引用检查保证 ID 存在且文本提及主题，不能证明每个自然语言结论都被证据支持。
- 反思来源 ID 能证明引用了已有观察，不能自动证明推断正确。
- `reflection_changed_output` 只表示下一版 JSON 改变，不能单独证明反思造成了改善；
  应结合 `multi` 组、轨迹和约束结果判断。没有收益也是有效结论。
- 规则模型的反思行为是人为设计的，离线成功率只证明协议，不证明智能。
- 每次实验清空角色记忆；不新增长期数据库、后台服务或分布式部署。

测试：

```powershell
python -m unittest p4_multi_agent_cowork.practice.test_practice -v
```
