"""Run from repository root: python -m p3_memory_and_context.practice.base_demo."""
import argparse
import json
import os
from pathlib import Path

from practice_common.model_adapter import DeepSeekAdapter, load_deepseek_key
from practice_common.runtime import ROOT, Trace, load_json, load_jsonl, save_json
from .embeddings import get_embedder
from .solution import run

HERE = Path(__file__).parent


def load_notes():
    """Read current notes instead of relying on the scaffold's old export."""
    records = []
    for path in sorted(ROOT.glob("p*/[Nn]ote.md")):
        text = path.read_text(encoding="utf-8")
        for number, paragraph in enumerate(text.split("\n\n"), 1):
            if len(paragraph.strip()) >= 25:
                records.append(dict(doc_id=path.parent.name, paragraph_id=str(number),
                                    source=path.relative_to(ROOT).as_posix(), text=paragraph.strip()))
    return records or load_jsonl(ROOT / "data/corpus.jsonl")


def main():
    parser = argparse.ArgumentParser(description="P3 base RAG step-in demo")
    parser.add_argument("--provider", choices=["offline", "deepseek"], default="offline")
    parser.add_argument("--embedding", choices=["hash", "local", "api"], default="local")
    parser.add_argument("--input", type=Path, default=HERE / "data/base_input.json")
    parser.add_argument("--step", action="store_true", help="Pause after each stage; no hidden reasoning is logged")
    parser.add_argument("--prepare", action="store_true", help="Download/load embedding model only")
    args = parser.parse_args()
    os.environ["P3_EMBEDDING_PROVIDER"] = args.embedding
    if args.prepare:
        os.environ["P3_DOWNLOAD_MODEL"] = "1"
    embedder = get_embedder()
    if args.prepare:
        print(json.dumps({"embedding": embedder.name, "dimensions": len(embedder.encode(["本地模型准备完成"])[0])}, ensure_ascii=False))
        return 0
    payload = load_json(args.input)
    config = load_json(HERE / "config.json")
    # Debugger/interactive observation time must not exhaust the normal 30s run budget.
    config["timeout_seconds"] = 3600 if args.step or os.environ.get("P3_DEBUG") else 120
    config["context_token_budget"] = 6000  # conservative UTF-8-byte estimate, not a tokenizer
    config["reserve_output_tokens"] = 800
    config["reserve_tool_tokens"] = 400
    model = None
    if args.provider == "deepseek":
        key = load_deepseek_key(ROOT)
        if not key:
            parser.error("Set DEEPSEEK_API_KEY or fill ignored api-key.txt")
        model = DeepSeekAdapter(key, model_name=os.environ.get("MODEL_NAME", "deepseek-chat"),
                                max_calls=1, timeout_seconds=60, max_output_tokens=config["reserve_output_tokens"])
    def observe(stage, data):
        print("\n[" + stage + "]", json.dumps(data, ensure_ascii=False, indent=2))
        if args.step:
            input("Enter 继续；也可在 solution.py 对应函数设置断点 > ")
    result = run(payload, model=model, embedder=embedder, corpus=load_notes(), config=config,
                 trace=Trace(HERE / "artifacts/base_trace.jsonl"), artifact_dir=HERE / "artifacts",
                 observe=observe)
    save_json(HERE / "artifacts/base_result.json", result)
    print("\n结果：", result["status"], result.get("answer", result.get("error")))
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
