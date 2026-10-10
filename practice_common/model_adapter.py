# -*- coding: utf-8 -*-
"""Model adapters sharing the exercise's normalized respond interface."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelAdapter:
    def __init__(self, max_calls=8, timeout_seconds=30):
        self.model_name = os.environ.get("MODEL_NAME", "")
        self.base_url = os.environ.get("MODEL_BASE_URL", "")
        self.max_calls = max_calls
        self.timeout_seconds = timeout_seconds
        self.calls = 0
        self.total_usage = {}

    def respond(self, messages, tools=None):
        raise NotImplementedError()


class DeepSeekAdapter(ModelAdapter):
    """DeepSeek chat-completions adapter with normalized tool-call output."""

    def __init__(self, api_key, model_name="deepseek-chat", max_calls=8,
                 timeout_seconds=30, base_url="https://api.deepseek.com/chat/completions"):
        super().__init__(max_calls=max_calls, timeout_seconds=timeout_seconds)
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url

    def respond(self, messages, tools=None):
        if self.calls >= self.max_calls:
            raise RuntimeError("model_call_budget_exhausted")

        body = {
            "model": self.model_name,
            "messages": self._prepare_messages(messages),
        }
        if tools:
            body["tools"] = [_tool_schema(name) for name in tools]
            body["tool_choice"] = "auto"

        request = Request(
            self.base_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError("deepseek_http_error_{}: {}".format(error.code, detail))
        except URLError as error:
            raise RuntimeError("deepseek_connection_error: {}".format(error.reason))

        self.calls += 1
        usage = payload.get("usage") or {}
        for key, value in usage.items():
            if isinstance(value, (int, float)):
                self.total_usage[key] = self.total_usage.get(key, 0) + value

        message = (payload.get("choices") or [{}])[0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if tool_calls:
            call = tool_calls[0]
            function = call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments", "{}"))
            except json.JSONDecodeError:
                arguments = {}
            return {
                "type": "tool_call",
                "call_id": call.get("id", "call-{}".format(self.calls)),
                "name": function.get("name", ""),
                "arguments": arguments,
                "usage": usage,
            }

        return {
            "type": "final",
            "answer": message.get("content") or "",
            "usage": usage,
        }

    @staticmethod
    def _prepare_messages(messages):
        prepared = []
        for message in messages:
            item = dict(message)
            content = item.get("content")
            if item.get("role") == "assistant" and isinstance(content, dict):
                item["content"] = ""
                item["tool_calls"] = [{
                    "id": content.get("call_id", "call-unknown"),
                    "type": "function",
                    "function": {
                        "name": content.get("name", ""),
                        "arguments": json.dumps(
                            content.get("arguments") or {}, ensure_ascii=False
                        ),
                    },
                }]
            if item.get("role") == "tool" and "tool_call_id" not in item:
                item["tool_call_id"] = item.get("call_id", "call-unknown")
            item.pop("call_id", None)
            prepared.append(item)
        return prepared


def load_deepseek_key(root):
    """Load a key from the environment first, then the ignored local key file."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    path = Path(root) / "api-key.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def _tool_schema(name):
    schemas = {
        "search_notes": {
            "type": "function",
            "function": {
                "name": "search_notes",
                "description": "Search the local course notes by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        "read_note": {
            "type": "function",
            "function": {
                "name": "read_note",
                "description": "Read one exact paragraph from the local course notes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "paragraph_id": {"type": "string"},
                    },
                    "required": ["doc_id", "paragraph_id"],
                    "additionalProperties": False,
                },
            },
        },
    }
    return schemas.get(name, {
        "type": "function",
        "function": {
            "name": name,
            "description": "Exercise tool.",
            "parameters": {"type": "object", "properties": {}},
        },
    })
