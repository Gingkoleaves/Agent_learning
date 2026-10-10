# -*- coding: utf-8 -*-
"""One-time scaffold creation. Refuses to overwrite existing chapter work."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = [
    ("p1_basic_concepts", "手写 Agent 与固定 workflow", [
        ("search_notes", "query, corpus", "实现关键词搜索，返回可定位的证据列表"),
        ("read_note", "doc_id, paragraph_id, corpus", "精确读取段落，缺失时给出明确错误"),
        ("run_workflow", "payload, **context", "固定搜索→读取→回答流程，作为对照"),
        ("run_agent", "payload, **context", "实现动作→执行→观察循环、终止条件及预算限制"),
        ("run", "payload, **context", "根据 payload.mode 分派 agent/workflow，返回答案、引用与统计"),
    ], {"mode": "agent", "question": "比较 ReAct 与固定 workflow，并给出来源"},
     "补齐 10 题：单资料、跨资料、无答案；至少 3 个多轮查证案例。", "先完成 search_notes/read_note，再 workflow，最后 agent。"),
    ("p2_function_calling", "可靠工具调用与 MCP", [
        ("validate_arguments", "tool_name, arguments, corpus", "校验字段、日期与来源 ID"),
        ("create_study_task", "title, due_date, source_ids, request_id, store", "实现持久化写入与 request_id 幂等，返回任务 ID"),
        ("get_study_task", "task_id, store", "读取真实存储状态"),
        ("dispatch_calls", "calls, registry, **context", "处理多个工具请求，保持每个调用 ID 和结果关联"),
        ("run", "payload, **context", "实现原生工具调用闭环、错误恢复与调用预算"),
    ], {"question": "查询 Toolformer，保存学习任务后读回确认", "due_date": "2026-10-16", "request_id": "sample-p2-001", "fault": None},
     "补齐 12 题，至少 4 题无需工具；加入非法参数、暂时失败、写成功但响应丢失。", "先存储和参数校验，再多调用分派，最后模型接口与 MCP。"),
    ("p3_memory_and_context", "RAG 与分层记忆", [
        ("build_index", "corpus, **context", "构造带来源和定位信息的 chunk，embedding 后持久化索引"),
        ("retrieve", "query, index, k=5", "返回 top-k 证据并保留定位信息"),
        ("update_profile", "user_id, facts, store", "按用户更新档案，保留来源与时间，新值覆盖有效旧值"),
        ("build_context", "messages, profile, evidence, strategy, token_budget", "实现截断、摘要、摘要加记忆检索，预留工具与回答空间"),
        ("run", "payload, **context", "串联索引、记忆、上下文和回答，提供关键词检索对照"),
    ], {"user_id": "learner-a", "question": "按我的进度安排今天学习", "facts": {"completed": ["ReAct"], "minutes_per_day": 45}, "strategy": "summary_retrieval"},
     "建立 >=100 个有效 chunk；补齐 15 个证据题、3 个无答案题、3 段各 20 轮对话。", "先索引与检索，再跨会话档案，最后上下文策略对照。"),
    ("p4_multi_agent_cowork", "角色协作与反思", [
        ("build_team", "profiles, **context", "用 AutoGen 或 CrewAI 创建独立角色与记忆"),
        ("route_message", "message, team", "校验消息契约并定向传递，处理角色超时"),
        ("reflect", "observations, **context", "生成带来源的反思，区分事实和推断"),
        ("validate_plan", "plan, profiles, corpus", "程序验证时间交集、时长、分工与证据 ID"),
        ("run", "payload, **context", "运行有限轮协作，对比单角色、无反思、有反思三种模式"),
    ], {"mode": "multi_reflection", "task_id": "discussion-001", "topic": "ReAct / Toolformer / MemGPT", "fault": None},
     "补齐 8 个场景，覆盖时间冲突、伪造引用、角色缺席；固定三组总调用预算。", "先验证计划和消息，再框架协作，最后反思消融。"),
    ("p5_agent_framework", "框架迁移与恢复", [
        ("build_graph", "**context", "用 LangGraph 创建有类型状态、校验回路、确认及保存节点"),
        ("resume_session", "session_id, decision, **context", "读取持久化检查点并恢复，正确区分用户确认状态"),
        ("run_sdk_baseline", "payload, **context", "用 OpenAI Agents SDK 实现小型同题对照"),
        ("run", "payload, **context", "分派新建/恢复与框架对照，外部写入复用第 2 章幂等工具"),
    ], {"mode": "langgraph", "session_id": "session-001", "question": "生成三天学习计划，确认后保存", "decision": None, "resume": False},
     "补齐 10 个固定输入；分别在检索后、等待确认、写入后中断，保存恢复证据。", "先定义 state.py，再搭图，然后确认/持久化/中断，最后 SDK 对照。"),
    ("p6_evaluation", "评测与可观测性", [
        ("reset_environment", "initial_state, **context", "每次评测恢复独立初始数据库及会话"),
        ("evaluate_case", "case, actual, final_state", "按事实、引用、动作规则和数据库终态判分"),
        ("summarize", "results", "计算单次成功率、三次全成功比例、调用统计和 p50/p95 耗时"),
        ("configure_observability", "**context", "接入 OpenTelemetry 父子 span 和一条 LangSmith trace"),
        ("run", "payload, **context", "运行 30 题各 3 次，保留原始结果，单独执行未参与调试题"),
    ], {"repeats": 3, "suite": "development", "agent_chapter": 5},
     "补齐 30 题（5 类各 6 题）及独立的 6 题 holdout；写真实预期终态与规则。", "先人工确定标准，再环境重置与判分，最后 trace、汇总及修复对照。"),
]


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("Refusing to overwrite: " + str(path))
    path.write_text(content, encoding="utf-8")


def json_file(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    records = []
    for doc_id, relative in [("p1-note", "p1_basic_concepts/Note.md"),
                             ("p2-note", "p2_function_calling/note.md"),
                             ("p3-note", "p3_memory_and_context/Note.md")]:
        text = (ROOT / relative).read_text(encoding="utf-8-sig")
        for index, paragraph in enumerate(re.split(r"\n\s*\n", text), 1):
            if paragraph.strip():
                records.append(dict(doc_id=doc_id, paragraph_id=str(index), source=relative, text=paragraph.strip()))
    write(ROOT / "data/corpus.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    for number, (folder, title, functions, payload, data_requirement, order) in enumerate(CHAPTERS, 1):
        chapter = ROOT / folder / "practice"
        write(ROOT / folder / "__init__.py", "")
        write(chapter / "__init__.py", "")
        source = '# -*- coding: utf-8 -*-\n"""Student implementations for chapter %d. See README.md and tasks.json."""\nfrom practice_common.runtime import todo\n' % number
        tasks = []
        for index, (name, signature, description) in enumerate(functions, 1):
            task_id = "P{}-{:02d}".format(number, index)
            source += '\n\ndef {}({}):\n    """{}: {}."""\n    # TODO({}): implement; do not replace with a constant fixture answer.\n    todo({!r}, {!r})\n'.format(name, signature, task_id, description, task_id, task_id, description)
            tasks.append(dict(id=task_id, file="solution.py:" + name, description=description))
        write(chapter / "solution.py", source)
        json_file(chapter / "tasks.json", tasks)
        json_file(chapter / "config.json", dict(max_model_calls=8 if number != 4 else 18,
                                                max_rounds=6 if number == 4 else 8, timeout_seconds=30,
                                                context_token_budget=2000, reserve_output_tokens=500))
        json_file(chapter / "data/input.json", payload)
        json_file(chapter / "data/responses.json", [
            dict(type="tool_call", call_id="call-001", name="search_notes", arguments=dict(query="ReAct")),
            dict(type="final", answer="这是模拟回复；不是实际资料检索的答案。", citations=[]),
        ])
        sample_case = dict(id="p{}-sample-001".format(number), fixture_only=True, input=payload,
                           expected_facts=[], expected_evidence_ids=[], initial_state={},
                           expected_final_state=None, allowed_actions=[], forbidden_actions=[],
                           user_script=[], annotation_status="TODO: 人工补全后才能用于正式评测")
        write(chapter / "data/cases.jsonl", json.dumps(sample_case, ensure_ascii=False) + "\n")
        write(chapter / "artifacts/.gitkeep", "")
        write(chapter / "evidence/.gitkeep", "")
        write(chapter / "requirements.txt", "# Add and pin only dependencies actually used by this chapter.\n")
        write(chapter / "report.md", "# 第 {} 章实验报告\n\n## 配置与完成清单\n\n- 模型/版本/参数：待填\n- 依赖版本：待填\n- 完成的 TODO：待填\n- 数据规模与标注方法：待填\n\n## 对照结果\n\n| 方案 | 正确率 | 引用有效率 | 模型调用 | 工具调用 | 耗时 | token usage |\n| --- | --- | --- | --- | --- | --- | --- |\n| 待填 | | | | | | |\n\n## 两个失败案例\n\n1. 输入、实际轨迹、预期、失败原因、修复：待填\n2. 输入、实际轨迹、预期、失败原因、修复：待填\n\n## 验收证据\n\n- 将人工核对的轨迹放入 evidence/，列出文件与运行命令。\n- 未完成部分、限制和实际差距：待填\n\n## 判断\n\n机制解决了什么失败、付出什么成本、有什么有效或无效的证据：待填\n".format(number))
        checklist = "\n".join("- [ ] `{id}` — `{file}`：{description}".format(**task) for task in tasks)
        write(chapter / "README.md", "# 第 {n} 章：{title}\n\n## 已提供的基础设施\n\n公共 JSON/JSONL 读写、模拟模型、调用计数、基础文件存储、日志、章节 CLI、启动语料与报告模板。`demo` 只验证这些设施，不执行本章算法。配置中的预算必须在你写的循环中执行，框架的 timeout/取消也需要你接入。\n\n## 你必须完成\n\n{checklist}\n\n- [ ] 模型适配：将真实模型响应转换为算法所用结构，传回真实工具结果，记录 usage。\n- [ ] 数据扩充：{data_requirement}\n- [ ] 故障注入、对照实验和 report.md；逐条对照根目录 PRACTICE_TASKS.md 的本章验收。\n\n## 推荐顺序\n\n{order}\n\n## 运行\n\n从仓库根目录执行：\n\n```powershell\npython practice.py {n} status\npython practice.py {n} demo\npython practice.py {n} run\npython practice.py {n} run --input {folder}/practice/data/input.json\n```\n\n初始 `run` 返回 TODO（退出码 2）是预期行为。实现 run 时串联其它函数，不要用样例固定答案绕过算法。框架/MCP 入口见本章额外文件；先安装你选定并锁定的依赖。\n\n## 输入和输出契约\n\n`data/input.json` 是最小输入；`data/responses.json` 是简单模拟动作，不代表每章完整轨迹。你需要按实际算法扩充模拟脚本。`data/cases.jsonl` 只有一条未标注样例，不是正式评测集。\n\n公共入口 `run(payload, **context)` 接收 model、corpus、trace、config、artifact_dir。输出必须是 JSON 可序列化字典，建议包含 status、answer/plan、citations、metrics。工具调用统一保留 call_id；证据保留 doc_id 和 paragraph_id（第 3 章扩充 chunk_id）。\n\n每次 run 自动写 artifacts/run.jsonl。正式证据复制到 evidence/；临时数据库、检查点、索引都放 artifacts/。跨章复用前面的 solution 模块；原始测例和人工标注继续纳入 Git。\n".format(n=number, title=title, checklist=checklist, data_requirement=data_requirement, order=order, folder=folder))


if __name__ == "__main__":
    main()
