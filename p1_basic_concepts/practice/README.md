# 第 1 章：手写 Agent 与固定 workflow

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P1-01` — `solution.py:search_notes`：实现关键词搜索，返回可定位的证据列表
- [ ] `P1-02` — `solution.py:read_note`：精确读取段落，缺失时给出明确错误
- [ ] `P1-03` — `solution.py:run_workflow`：固定搜索→读取→回答流程，作为对照
- [ ] `P1-04` — `solution.py:run_agent`：实现动作→执行→观察循环、终止条件及预算限制
- [ ] `P1-05` — `solution.py:run`：根据 payload.mode 分派 agent/workflow，返回答案、引用与统计

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：补齐 10 题：单资料、跨资料、无答案；至少 3 个多轮查证案例。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

先完成 search_notes/read_note，再 workflow，最后 agent。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 1 status
.\scripts\practice.ps1 1 demo
.\scripts\practice.ps1 1 run
.\scripts\practice.ps1 1 run --input p1_basic_concepts/practice/data/input.json
```

默认使用 `ScriptedModel`。要使用 DeepSeek，确保根目录的 `api-key.txt` 中只有 API key，或设置 `DEEPSEEK_API_KEY`，然后在 bash 中运行：

```bash
MODEL_PROVIDER=deepseek python practice.py 1 run
```

Windows PowerShell 使用：

```powershell
$env:MODEL_PROVIDER = "deepseek"
python practice.py 1 run
```

可选地用 `MODEL_NAME` 覆盖模型名；默认是 `deepseek-chat`。密钥不会写入 trace 或输出。

初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。
