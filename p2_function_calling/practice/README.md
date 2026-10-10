# 第 2 章：可靠工具调用与 MCP

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P2-01` — `solution.py:validate_arguments`：校验字段、日期与来源 ID
- [ ] `P2-02` — `solution.py:create_study_task`：实现持久化写入与 request_id 幂等，返回任务 ID
- [ ] `P2-03` — `solution.py:get_study_task`：读取真实存储状态
- [ ] `P2-04` — `solution.py:dispatch_calls`：处理多个工具请求，保持每个调用 ID 和结果关联
- [ ] `P2-05` — `solution.py:run`：实现原生工具调用闭环、错误恢复与调用预算

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：补齐 12 题，至少 4 题无需工具；加入非法参数、暂时失败、写成功但响应丢失。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

额外必须完成：`mcp_server.py` 的 `P2-MCP-SERVER`、`mcp_client.py` 的 `P2-MCP-CLIENT`。从根目录分别用 `python -m p2_function_calling.practice.mcp_server` 和 `python -m p2_function_calling.practice.mcp_client` 启动。故障清单在 `data/faults.json`；你负责把它们实际注入工具。

先存储和参数校验，再多调用分派，最后模型接口与 MCP。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 2 status
.\scripts\practice.ps1 2 demo
.\scripts\practice.ps1 2 run
.\scripts\practice.ps1 2 run --input p2_function_calling/practice/data/input.json
```

初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。


