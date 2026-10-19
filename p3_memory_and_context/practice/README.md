# 第 3 章：RAG 与分层记忆

**当前实现：** P3-01～05 已提供基础闭环，按 [BASE_WALKTHROUGH.md](BASE_WALKTHROUGH.md) 使用 DeepSeek + 本地 BGE 单步观察。正式数据集与质量验收仍待完成。P3-06～10 仍为 TODO。下方清单用于跟踪完整作业，不代表验收已经通过。

本章分两阶段：P3-01～05 完成基础 RAG 与档案管理；P3-06～10 完成新增的 [MemGPT 式上下文与外部存储实践](MEMGPT_PRACTICE.md)。新增内容也是待实现作业，当前 demo 不执行这些机制。

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P3-01` — `solution.py:build_index`：构造带来源和定位信息的 chunk，embedding 后持久化索引
- [ ] `P3-02` — `solution.py:retrieve`：返回 top-k 证据并保留定位信息
- [ ] `P3-03` — `solution.py:update_profile`：按用户更新档案，保留来源与时间，新值覆盖有效旧值
- [ ] `P3-04` — `solution.py:build_context`：实现截断、摘要、摘要加记忆检索，预留工具与回答空间
- [ ] `P3-05` — `solution.py:run`：串联索引、记忆、上下文和回答，提供关键词检索对照

- [ ] `P3-06` — `solution.py:init_memory`：分层状态、持久化和用户隔离
- [ ] `P3-07` — `solution.py:manage_context`：FIFO、历史存储、预算警告和移出策略
- [ ] `P3-08` — `solution.py:execute_memory_tool`：记忆工具执行与返回消息配对
- [ ] `P3-09` — `solution.py:run_memory_agent`：heartbeat/yield、事件唤醒和链式调用
- [ ] `P3-10` — `solution.py:evaluate_memory`：固定场景与四种上下文策略对照

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：建立 >=100 个有效 chunk；补齐 15 个证据题、3 个无答案题、3 段各 20 轮对话。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

`data/conversation.json` 提供跨会话更新和用户隔离的起点；你需要扩充消息并标注期望档案。输入事实只是样例，不会自动写入记忆。

先索引与检索，再跨会话档案，最后上下文策略对照。

随后按 MEMGPT_PRACTICE.md 实现分层存储、队列管理、函数执行器和事件循环。复用已有模型适配器与日志；先用模拟调用验证协议，再少量真实调用证明模型会自主使用记忆工具。最终对照增加 MemGPT 式记忆循环作为第四组。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 3 status
.\scripts\practice.ps1 3 demo
.\scripts\practice.ps1 3 run
.\scripts\practice.ps1 3 run --input p3_memory_and_context/practice/data/input.json
```

基础 `run` 现在串联索引、档案、上下文和生成；默认 scripted 模式只验证数据流。`mode="memgpt"` 仍返回 TODO。推荐使用 BASE_WALKTHROUGH.md 的专用演示入口，它读取最新笔记并默认使用本地语义 embedding。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。


