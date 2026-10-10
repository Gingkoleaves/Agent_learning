# -*- coding: utf-8 -*-
"""Student implementations for chapter 1. See README.md and tasks.json."""
import json
import re

from practice_common.runtime import todo


def search_notes(query, corpus):
    """P1-01: 实现关键词搜索，返回可定位的证据列表."""
    if not isinstance(query, str) or not query.strip():
        return []

    keywords = [part.casefold() for part in re.findall(r"[\w\u4e00-\u9fff]+", query)]
    if not keywords:
        return []

    matches = []
    for position, note in enumerate(corpus or []):
        text = str(note.get("text", ""))
        searchable_text = text.casefold()
        matched_keywords = [keyword for keyword in keywords if keyword in searchable_text]
        if not matched_keywords:
            continue

        result = dict(note)
        result["matched_keywords"] = sorted(set(matched_keywords))
        result["score"] = len(set(matched_keywords))
        if " ".join(keywords) in searchable_text:
            result["score"] += 1
        matches.append((-result["score"], position, result))

    matches.sort(key=lambda item: (item[0], item[1]))
    return [result for _, _, result in matches]


def read_note(doc_id, paragraph_id, corpus):
    """P1-02: 精确读取段落，缺失时给出明确错误."""
    for note in corpus or []:
        if (str(note.get("doc_id")) == str(doc_id)
                and str(note.get("paragraph_id")) == str(paragraph_id)):
            return dict(note)

    raise ValueError(
        "note paragraph not found: doc_id={!r}, paragraph_id={!r}".format(
            doc_id, paragraph_id
        )
    )


def run_workflow(payload, **context):
    """P1-03: 固定搜索→读取→回答流程，作为对照."""
    question = payload.get("question", payload.get("query", ""))
    corpus = context.get("corpus", [])
    search_results = search_notes(question, corpus)
    if not search_results:
        return {
            "status": "no_evidence",
            "answer": "未找到相关证据。",
            "citations": [],
            "metrics": {"model_calls": 0, "tool_calls": 1},
        }

    evidence = []
    for result in search_results[:3]:
        evidence.append(read_note(result["doc_id"], result["paragraph_id"], corpus))

    answer = "\n\n".join(note.get("text", "") for note in evidence)
    model = context.get("model")
    model_calls = 0
    if model is not None:
        prompt = {
            "role": "user",
            "content": "问题：{}\n请只根据以下证据回答：\n{}".format(
                question, json.dumps(evidence, ensure_ascii=False)
            ),
        }
        response = model.respond([prompt])
        model_calls = 1
        if response.get("type") == "final" and response.get("answer"):
            answer = response["answer"]

    return {
        "status": "completed",
        "answer": answer,
        "citations": [_citation(note) for note in evidence],
        "metrics": {
            "model_calls": model_calls,
            "tool_calls": 1 + len(evidence),
            "search_results": len(search_results),
            "read_results": len(evidence),
            "usage": _usage(model),
        },
    }


def run_agent(payload, **context):
    """P1-04: 实现动作→执行→观察循环、终止条件及预算限制."""
    question = payload.get("question", payload.get("query", ""))
    corpus = context.get("corpus", [])
    config = context.get("config", {})
    model = context.get("model")
    max_rounds = int(config.get("max_rounds", 8))
    max_model_calls = int(config.get("max_model_calls", max_rounds))
    if model is None:
        return _result("error", "缺少模型，无法运行 Agent。", [], model_calls=0)

    messages = [{"role": "user", "content": question}]
    citations = []
    model_calls = 0
    tool_calls = 0
    trace = context.get("trace")

    for round_number in range(max_rounds):
        if model_calls >= max_model_calls:
            return _result(
                "budget_exhausted", "模型调用预算耗尽，未能完成任务。", citations,
                model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model),
            )
        try:
            response = model.respond(messages, tools=["search_notes", "read_note"])
            model_calls += 1
        except RuntimeError as error:
            return _result(
                "budget_exhausted", "模型调用预算耗尽，未能完成任务。", citations,
                model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model), error=str(error),
            )

        _emit(trace, "model_response", round=round_number + 1, response=response)
        if response.get("type") == "final":
            return _result(
                "completed", response.get("answer", ""), citations,
                model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model),
            )

        if response.get("type") != "tool_call":
            return _result(
                "invalid_action", "模型返回了无法识别的动作。", citations,
                model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model),
            )

        call_id = response.get("call_id", "call-{}".format(model_calls))
        name = response.get("name")
        arguments = response.get("arguments") or {}
        observation = _execute_tool(name, arguments, corpus)
        tool_calls += 1
        for note in observation.get("evidence", []):
            citation = _citation(note)
            if citation not in citations:
                citations.append(citation)
        _emit(trace, "tool_result", call_id=call_id, name=name, observation=observation)
        messages.append({"role": "assistant", "content": response})
        messages.append({
            "role": "tool",
            "call_id": call_id,
            "content": json.dumps(observation, ensure_ascii=False),
        })

    return _result(
        "max_rounds", "达到最大轮数，未能完成任务。", citations,
        model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model),
    )


def run(payload, **context):
    """P1-05: 根据 payload.mode 分派 agent/workflow，返回答案、引用与统计."""
    mode = payload.get("mode")
    if mode == "workflow":
        return run_workflow(payload, **context)
    if mode == "agent":
        return run_agent(payload, **context)
    return _result("invalid_input", "不支持的运行模式：{!r}".format(mode), [])


def _citation(note):
    return {
        "doc_id": note["doc_id"],
        "paragraph_id": note["paragraph_id"],
    }


def _result(status, answer, citations, **metrics):
    return {
        "status": status,
        "answer": answer,
        "citations": citations,
        "metrics": metrics,
    }


def _emit(trace, event, **fields):
    if trace is not None:
        trace.emit(event, **fields)


def _usage(model):
    return dict(getattr(model, "total_usage", {}) or {})


def _execute_tool(name, arguments, corpus):
    if name == "search_notes":
        results = search_notes(arguments.get("query", ""), corpus)
        return {"evidence": results, "count": len(results)}
    if name == "read_note":
        try:
            note = read_note(arguments["doc_id"], arguments["paragraph_id"], corpus)
        except (KeyError, ValueError) as error:
            return {"error": str(error), "evidence": []}
        return {"evidence": [note]}
    return {"error": "unknown_tool: {!r}".format(name), "evidence": []}