# -*- coding: utf-8 -*-
"""Debug driver: call the student's search implementation with actual corpus."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from practice_common.runtime import load_jsonl
from p1_basic_concepts.practice.solution import search_notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="ReAct agent")
    args = parser.parse_args()
    corpus = load_jsonl(ROOT / "data/corpus.jsonl")
    # Set a breakpoint here, then press F11 to enter search_notes.
    results = search_notes(args.query, corpus)
    print(json.dumps(results[:5], ensure_ascii=False, indent=2))
    print("Total matches:", len(results))


if __name__ == "__main__":
    main()
