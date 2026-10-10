# -*- coding: utf-8 -*-
"""Infrastructure smoke checks, not exercise acceptance tests."""
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from practice_common.cli import CHAPTERS
from practice_common.runtime import JsonStore, ScriptedModel, Trace, load_json, load_jsonl


def main():
    temporary_root = ROOT / "tmp" / "scaffold-check"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=str(temporary_root)) as temporary:
        temp = Path(temporary)
        store = JsonStore(temp / "state.json")
        assert store.read() == {}
        store.write({"minutes": 20})
        assert store.read() == {"minutes": 20}
        trace = Trace(temp / "trace.jsonl")
        trace.emit("tool", call_id="call-1", result={"ok": True})
        assert load_jsonl(trace.path)[0]["call_id"] == "call-1"
        model = ScriptedModel([{"type": "final"}], max_calls=1)
        assert model.respond([])["type"] == "final"
        try:
            model.respond([])
        except RuntimeError as error:
            assert str(error) == "model_call_budget_exhausted"
        else:
            raise AssertionError("Model budget not enforced")
    corpus = load_jsonl(ROOT / "data/corpus.jsonl")
    assert corpus and all(set(["doc_id", "paragraph_id", "source", "text"]) <= row.keys() for row in corpus)
    for number, folder in CHAPTERS.items():
        chapter = ROOT / folder / "practice"
        tasks = load_json(chapter / "tasks.json")
        module = importlib.import_module(folder + ".practice.solution")
        for task in tasks:
            if task["file"].startswith("solution.py:"):
                assert callable(getattr(module, task["file"].split(":", 1)[1]))
        for mode, exit_codes in [("status", (0,)), ("demo", (0,)), ("run", (0, 2))]:
            result = subprocess.run([sys.executable, str(ROOT / "practice.py"), str(number), mode],
                                    cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert result.returncode in exit_codes, (number, mode, result.stdout, result.stderr)
        assert load_jsonl(chapter / "artifacts/run.jsonl")[-1]["event"] in ("incomplete", "result")
        print("Chapter {}: file contracts, demo and run exit verified".format(number))
    print("Infrastructure checks passed; student algorithms and course acceptance are pending.")


if __name__ == "__main__":
    main()
