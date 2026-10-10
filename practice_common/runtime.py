"""Standard-library infrastructure, compatible with Python 3.9+."""
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


class ExerciseIncomplete(NotImplementedError):
    """A student-owned implementation has not been written yet."""


def todo(task_id: str, description: str):
    raise ExerciseIncomplete("{}: {}".format(task_id, description))


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value: Any) -> None:
    """Atomic single-process replacement; not a concurrent database."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temporary), str(path))


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class Trace:
    """Append-only local events; OpenTelemetry integration is a chapter 6 TODO."""
    def __init__(self, path: Path):
        self.path = path
        self.started = time.monotonic()

    def emit(self, event: str, **fields: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = dict(event=event, elapsed_seconds=time.monotonic() - self.started, **fields)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class ScriptedModel:
    """Deterministic fixture responses; no network, keys or reasoning simulation."""
    def __init__(self, responses: List[Dict[str, Any]], max_calls: int = 8):
        self.responses = responses
        self.max_calls = max_calls
        self.calls = 0
        self.history = []

    def respond(self, messages: List[Dict[str, Any]], tools=None) -> Dict[str, Any]:
        if self.calls >= self.max_calls:
            raise RuntimeError("model_call_budget_exhausted")
        if self.calls >= len(self.responses):
            raise RuntimeError("scripted_responses_exhausted")
        self.history.append(dict(messages=list(messages), tools=tools))
        response = self.responses[self.calls]
        self.calls += 1
        return response


class JsonStore:
    """Basic persistence only; validation and idempotency are student work."""
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> Dict[str, Any]:
        return load_json(self.path) if self.path.exists() else {}

    def write(self, value: Dict[str, Any]) -> None:
        save_json(self.path, value)
