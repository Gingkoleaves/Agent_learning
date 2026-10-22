"""运行入口与八场景对照。算法在 solution.py，本文件只负责装配和保存。"""
import json

from practice_common.runtime import Trace, load_json, load_jsonl, save_json
from .models import make_model, resolve_provider
from .planning import validate_plan
from .solution import HERE, MODES, run


def case_input(case, mode):
    profiles = load_json(HERE / "data/profiles.json")
    for profile in profiles:
        changes = case.get("availability", {}).get(profile["id"], {})
        profile["available"].update(changes)
    return {"task_id": case["id"], "mode": mode, "fault": case.get("fault"),
            "topic": "ReAct / Toolformer / MemGPT", "profiles": profiles}


def evaluate(provider=None):
    """全部组合都从干净状态启动，使用相同资料和 18 次调用上限。"""
    provider = resolve_provider(provider)
    cases = load_jsonl(HERE / "data/cases.jsonl")
    corpus = load_jsonl(HERE / "data/corpus.jsonl")
    rows = []
    for case in cases:
        for mode in MODES:
            folder = HERE / "artifacts" / provider / case["id"] / mode
            # 每次评测清空旧轨迹，记录本次运行。
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "trace.jsonl").write_text("", encoding="utf-8")
            result = run(case_input(case, mode), model=make_model(provider),
                         corpus=corpus, artifact_dir=folder,
                         trace=Trace(folder / "trace.jsonl"))
            passed = result["status"] == case["expected_status"]
            if case["expected_status"] in ("completed", "degraded"):
                profiles = result.get("effective_profiles", [])
                passed = (passed and bool(profiles)
                          and not validate_plan(result["plan"], profiles, corpus)
                          and not validate_plan(result["next_plan"], profiles, corpus))
            if case.get("fault") in ("time_conflict", "forged_reference"):
                passed = passed and bool(result["repairs"])
            if case.get("fault") == "absent":
                passed = passed and result["missing"] == ["critic"]
            rows.append({"case": case["id"], "mode": mode, "passed": bool(passed),
                         "status": result["status"], "metrics": result["metrics"],
                         "repairs": len(result["repairs"]),
                         "changed_next_output": result.get("reflection_changed_output", False)})
            print(f"{provider:8} {case['id']:16} {mode:16} {result['status']:20} pass={bool(passed)}",
                  flush=True)
    summary = {"provider": provider, "passed": sum(r["passed"] for r in rows),
               "total": len(rows), "rows": rows}
    save_json(HERE / "artifacts" / provider / "evaluation.json", summary)
    return summary


def launch(provider=None, input_path=None, evaluate_all=False):
    provider = resolve_provider(provider)
    print(f"P4 provider: {provider}", flush=True)
    if evaluate_all:
        result = evaluate(provider)
        print(f"\n通过 {result['passed']}/{result['total']}。结果：artifacts/{provider}/evaluation.json")
        return int(result["passed"] != result["total"])
    payload = load_json(input_path or HERE / "data/input.json")
    result = run(payload, model=make_model(provider))
    # CLI 只展示需要读的内容；完整消息、角色记忆在 last_result.json 中。
    brief = {k: result.get(k) for k in ("status", "reason", "mode", "plan", "next_plan",
                                      "missing", "rounds", "metrics")}
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    print("完整轨迹：p4_multi_agent_cowork/practice/artifacts/run.jsonl")
    print("完整结果：p4_multi_agent_cowork/practice/artifacts/last_result.json")
    return int(result["status"] not in ("completed", "degraded", "infeasible"))
