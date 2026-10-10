# 第 4 章：角色协作与反思

## 已提供的基础设施

公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。

## 你必须完成

- [ ] `P4-01` — `solution.py:build_team`：用 AutoGen 或 CrewAI 创建独立角色与记忆
- [ ] `P4-02` — `solution.py:route_message`：校验消息契约并定向传递，处理角色超时
- [ ] `P4-03` — `solution.py:reflect`：生成带来源的反思，区分事实和推断
- [ ] `P4-04` — `solution.py:validate_plan`：程序验证时间交集、时长、分工与证据 ID
- [ ] `P4-05` — `solution.py:run`：运行有限轮协作，对比单角色、无反思、有反思三种模式

- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。
- [ ] 数据扩充：补齐 8 个场景，覆盖时间冲突、伪造引用、角色缺席；固定三组总调用预算。
- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。

## 推荐顺序

角色起点在 `data/profiles.json`，消息和议程类型在 `contracts.py`。你需要在 run 中加载角色，TypedDict 只声明字段，不执行运行时校验；消息路由与计划验证由你实现。

先验证计划和消息，再框架协作，最后反思消融。

## 运行

从仓库根目录执行（入口固定使用命名 Conda 环境 agent-learn）：

```powershell
.\scripts\practice.ps1 4 status
.\scripts\practice.ps1 4 demo
.\scripts\practice.ps1 4 run
.\scripts\practice.ps1 4 run --input p4_multi_agent_cowork/practice/data/input.json
```

初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。

## 输入和输出契约

`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。

公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。

每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。


