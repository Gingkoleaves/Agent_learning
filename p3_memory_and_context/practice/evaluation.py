"""Repeatable mechanism checks and context availability comparison, not QA accuracy."""
import json
from pathlib import Path

from practice_common.runtime import JsonStore, save_json, Trace
from .memory import DEFAULTS, init_memory, compose, manage_context, run_memory_agent
from .solution import build_context, DemoPolicy, seed_demo


def evaluate(payload, **context):
    root = Path(context.get("artifact_dir", Path(__file__).parent / "artifacts"))
    root.mkdir(parents=True, exist_ok=True)
    import uuid
    run_root = root / ("comparison-" + uuid.uuid4().hex[:8])
    run_root.mkdir()
    cfg = dict(DEFAULTS)
    trace = Trace(run_root / "trace.jsonl")
    state = seed_demo(run_root, cfg, trace)
    before_hidden = "青鹭" not in json.dumps(compose(state), ensure_ascii=False)
    question = "现在每天只有20分钟，请更新记忆。再查一下我之前说的项目代号，找不到不要猜。"
    history = [{"role": m["role"], "content": m["content"]} for m in state["recall"] if m["role"] == "user"]
    messages = history + [{"role": "user", "content": question}]
    results = []
    for strategy in ("truncate", "summary", "summary_retrieval"):
        allowance = cfg["context_token_budget"] - cfg["reserve_output_tokens"] - cfg["reserve_tool_tokens"]
        built = build_context(messages, state["working_context"], [], strategy, allowance)
        text = json.dumps(built["messages"], ensure_ascii=False)
        results.append(dict(strategy=strategy, target_available="青鹭" in text,
                            input_estimate=built["input_tokens_estimate"], model_calls=0, tool_calls=0,
                            note="context availability only; no answer generated"))
        save_json(run_root / (strategy + ".json"), built)
    agent = run_memory_agent({"user_id": state["user_id"], "session_id": "demo", "question": question},
                             artifact_dir=run_root, config=cfg, model=DemoPolicy(), trace=trace)
    results.append(dict(strategy="memgpt_scripted", target_available="青鹭" in agent["answer"],
                        input_estimate=agent["metrics"]["peak_input_estimate"],
                        model_calls=agent["metrics"]["model_calls"], tool_calls=agent["metrics"]["tool_calls"],
                        note="scripted tool policy; includes tool schema overhead, not QA accuracy"))
    save_json(run_root / "agent.json", agent)
    restored = init_memory(state["user_id"], "restart-check", JsonStore(run_root / "memory.json"))
    isolated = init_memory("other-user", "fresh", JsonStore(run_root / "memory.json"))
    idle = run_memory_agent({"user_id": state["user_id"], "session_id": "demo"},
                            artifact_dir=run_root, model=DemoPolicy(), config=cfg)
    checks = {
        "answer_absent_before_recall": before_hidden,
        "recall_chain_completed": agent["status"] == "yielded" and "青鹭" in agent["answer"] and agent["metrics"]["tool_calls"] == 4,
        "current_preference_updated": restored["working_context"]["facts"].get("minutes_per_day", {}).get("value") == 20,
        "old_preference_preserved": any(f.get("value") == 45 for f in restored["working_context"]["history"]),
        "new_session_empty_fifo": restored["fifo"] == [],
        "user_isolation": not isolated["recall"] and not isolated["working_context"]["facts"],
        "no_event_no_inference": idle["status"] == "waiting" and idle["metrics"]["model_calls"] == 0,
        "input_budget_respected": all(r["input_estimate"] <= allowance for r in results),
    }
    result = dict(checks=checks, mechanism_checks=len(checks), failures=sum(not passed for passed in checks.values()), errors=0,
                  comparison=results, artifacts=str(run_root.resolve()),
                  limitations="Synthetic case; same 11400-byte input cap, MemGPT also pays tool-schema overhead; target availability is not answer accuracy. No claim of MemGPT superiority.")
    save_json(root / "evaluation.json", result)
    return result
