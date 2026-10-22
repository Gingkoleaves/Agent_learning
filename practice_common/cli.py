# -*- coding: utf-8 -*-
import argparse
import importlib
import json
import os
from pathlib import Path

from practice_common.model_adapter import DeepSeekAdapter, load_deepseek_key
from practice_common.runtime import ExerciseIncomplete, ROOT, ScriptedModel, Trace, load_json, load_jsonl

CHAPTERS = {
    1: "p1_basic_concepts", 2: "p2_function_calling", 3: "p3_memory_and_context",
    4: "p4_multi_agent_cowork", 5: "p5_agent_framework", 6: "p6_evaluation",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agent learning practice scaffold")
    parser.add_argument("chapter", choices=[str(n) for n in CHAPTERS] + ["3-rag", "3-memgpt"],
                        help="Chapter number; 3-rag/3-memgpt also select the P3 mode")
    parser.add_argument("command", choices=["status", "demo", "run"])
    parser.add_argument("--input", type=Path, help="Override sample input JSON")
    parser.add_argument("--mode", choices=["rag", "memgpt"], help="P3 execution mode (default: rag)")
    parser.add_argument("--provider", choices=["scripted", "offline", "deepseek"], help="P3/P4 model provider")
    parser.add_argument("--evaluate", action="store_true", help="P3/P4: run evaluation")
    args = parser.parse_args(argv)
    chapter_selection = args.chapter.split("-", 1)
    args.chapter = int(chapter_selection[0])
    if len(chapter_selection) == 2 and args.mode is None:
        args.mode = chapter_selection[1]
    chapter = ROOT / CHAPTERS[args.chapter] / "practice"
    tasks = load_json(chapter / "tasks.json")
    if args.command == "status":
        print("Checklist only; this command does not certify completion.")
        for task in tasks:
            print("{} [{}] {}".format(task["id"], task["file"], task["description"]))
        return 0
    if args.chapter == 4 and args.command == "run":
        from p4_multi_agent_cowork.practice.experiment import launch
        return launch(args.provider, args.input, args.evaluate)
    if args.chapter == 3 and args.command == "run":
        from p3_memory_and_context.practice.solution import launch
        if args.evaluate:
            from p3_memory_and_context.practice.solution import evaluate_memory
            result = evaluate_memory({})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return int(result["failures"] > 0)
        provider = args.provider or os.environ.get("MODEL_PROVIDER", "scripted")
        return launch(args.mode or "rag", provider, args.input)
    trace = Trace(chapter / "artifacts" / (args.command + ".jsonl"))
    config = load_json(chapter / "config.json")
    payload = load_json(args.input or chapter / "data" / "input.json")
    corpus = load_jsonl(ROOT / "data" / "corpus.jsonl")
    provider = os.environ.get("MODEL_PROVIDER", "scripted").strip().lower()
    if provider == "deepseek":
        api_key = load_deepseek_key(ROOT)
        if not api_key:
            print("未找到 DeepSeek API key，请设置 DEEPSEEK_API_KEY 或填写 api-key.txt")
            return 2
        model = DeepSeekAdapter(
            api_key=api_key,
            model_name=os.environ.get("MODEL_NAME", "deepseek-chat"),
            max_calls=config["max_model_calls"],
            timeout_seconds=config["timeout_seconds"],
        )
    else:
        model = ScriptedModel(load_json(chapter / "data" / "responses.json"), config["max_model_calls"])
    trace.emit("start", chapter=args.chapter, mode=args.command)
    if args.command == "demo":
        response = model.respond([dict(role="user", content=payload)])
        trace.emit("fixture_response", response=response)
        print(json.dumps(dict(mode="infrastructure_demo", corpus_records=len(corpus),
                              input=payload, scripted_response=response), ensure_ascii=False, indent=2))
        print("Demo verified file loading, scripted model and JSONL logging only. Exercise not implemented.")
        return 0
    module = importlib.import_module(CHAPTERS[args.chapter] + ".practice.solution")
    try:
        result = module.run(payload, model=model, corpus=corpus, trace=trace,
                            config=config, artifact_dir=chapter / "artifacts")
    except ExerciseIncomplete as error:
        trace.emit("incomplete", reason=str(error))
        print("TODO — " + str(error))
        return 2
    trace.emit("result", result=result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
