# 第 5 章：框架迁移与恢复

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P5-01` — `solution.py:build_graph`：用 LangGraph 创建有类型状态、校验回路、确认及保存节点
- [ ] `P5-02` — `solution.py:resume_session`：读取持久化检查点并恢复，正确区分用户确认状态
- [ ] `P5-03` — `solution.py:run_sdk_baseline`：用 OpenAI Agents SDK 实现小型同题对照
- [ ] `P5-04` — `solution.py:run`：分派新建/恢复与框架对照，外部写入复用第 2 章幂等工具

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：补齐 10 个固定输入；分别在检索后、等待确认、写入后中断，保存恢复证据。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

额外必须完成：`state.py` 中 `P5-STATE` 的初始化、状态合并及合法迁移设计。`data/interruptions.json` 只列出中断场景；你要通过独立进程中断和恢复，证明持久化真实有效。

先定义 state.py，再搭图，然后确认/持久化/中断，最后 SDK 对照。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 5 status
.\scripts\practice.ps1 5 demo
.\scripts\practice.ps1 5 run
.\scripts\practice.ps1 5 run --input p5_agent_framework/practice/data/input.json
```

初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。


