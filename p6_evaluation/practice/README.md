# 第 6 章：评测与可观测性

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P6-01` — `solution.py:reset_environment`：每次评测恢复独立初始数据库及会话
- [ ] `P6-02` — `solution.py:evaluate_case`：按事实、引用、动作规则和数据库终态判分
- [ ] `P6-03` — `solution.py:summarize`：计算单次成功率、三次全成功比例、调用统计和 p50/p95 耗时
- [ ] `P6-04` — `solution.py:configure_observability`：接入 OpenTelemetry 父子 span 和一条 LangSmith trace
- [ ] `P6-05` — `solution.py:run`：运行 30 题各 3 次，保留原始结果，单独执行未参与调试题

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：补齐 30 题（5 类各 6 题）及独立的 6 题 holdout；写真实预期终态与规则。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

判分原则见 `RUBRIC.md`。`data/holdout.jsonl` 只是模板，正式评测器必须拒绝未标注 fixture，开发集和 holdout 分开报告。基础 JSONL 日志不等于完成了 OpenTelemetry/LangSmith 接入。

先人工确定标准，再环境重置与判分，最后 trace、汇总及修复对照。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 6 status
.\scripts\practice.ps1 6 demo
.\scripts\practice.ps1 6 run
.\scripts\practice.ps1 6 run --input p6_evaluation/practice/data/input.json
```

初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。


