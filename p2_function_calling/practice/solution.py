# -*- coding: utf-8 -*-
"""Reliable tool calling primitives for chapter 2."""
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4
from threading import RLock

from p1_basic_concepts.practice.solution import read_note, search_notes
from practice_common.runtime import JsonStore
from p2_function_calling.practice.operations import OperationJournal, WRITE_TOOLS, model_schemas

_WRITE_LOCK = RLock()


def validate_arguments(tool_name, arguments, corpus):
    """P2-01: 校验字段、日期与来源 ID."""
    arguments = arguments or {}
    if tool_name == "search_notes":
        if not isinstance(arguments.get("query"), str) or not arguments["query"].strip():
            raise ValueError("query is required")
        return True
    if tool_name == "read_note":
        if not isinstance(arguments.get("doc_id"), str) or not arguments["doc_id"].strip():
            raise ValueError("doc_id is required")
        if not isinstance(arguments.get("paragraph_id"), str) or not arguments["paragraph_id"].strip():
            raise ValueError("paragraph_id is required")
        return True
    if tool_name in WRITE_TOOLS:
        if 'request_id' in arguments or 'operation_id' in arguments:
            raise ValueError('write identifiers are managed by the host')
        updating = tool_name == 'update_study_task'
        if updating:
            if not isinstance(arguments.get('task_id'), str) or not arguments['task_id'].strip():
                raise ValueError('task_id is required')
            if not any(arguments.get(key) is not None for key in ('title', 'due_date', 'source_ids', 'status')):
                raise ValueError('provide at least one field to update')
            if arguments.get('status') is not None and arguments['status'] not in ('pending', 'completed'):
                raise ValueError('invalid task status')
        title = arguments.get('title')
        if (not updating or title is not None) and (not isinstance(title, str) or not title.strip()):
            raise ValueError('title is required')
        due_date = arguments.get('due_date')
        if not updating or due_date is not None:
            if not isinstance(due_date, str):
                raise ValueError('due_date must be YYYY-MM-DD')
            parsed = date.fromisoformat(due_date)
            if parsed.isoformat() != due_date:
                raise ValueError('due_date must be YYYY-MM-DD')
        source_ids = arguments.get('source_ids')
        if not updating or source_ids is not None:
            if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
                raise ValueError('source_ids must be a list of document IDs')
            known = {str(item.get('doc_id')) for item in corpus or []}
            unknown = [item for item in source_ids if item not in known]
            if unknown:
                raise ValueError('unknown source_ids: ' + ', '.join(unknown))
        return True
    if tool_name == "get_study_task":
        if not isinstance(arguments.get("task_id"), str) or not arguments["task_id"].strip():
            raise ValueError("task_id is required")
        return True
    raise ValueError("unknown_tool: {!r}".format(tool_name))


def _write_task(tool, arguments, operation_id, store):
    if not isinstance(operation_id, str) or not operation_id:
        raise ValueError('host operation_id is required')
    with _WRITE_LOCK:
        state = store.read()
        tasks = state.setdefault('tasks', {})
        operations = state.setdefault('operations', {})
        previous = operations.get(operation_id)
        if previous:
            if previous['tool'] != tool or previous['arguments'] != arguments:
                raise ValueError('operation_id reused with different arguments')
            return dict(previous['result'], idempotent=True)
        if tool == 'create_study_task':
            number = max([int(key[5:]) for key in tasks if key.startswith('task-') and key[5:].isdigit()] or [0]) + 1
            task_id = 'task-{:04d}'.format(number)
            task = dict(task_id=task_id, status='pending', **arguments)
        else:
            task_id = arguments['task_id']
            if task_id not in tasks:
                raise ValueError('study task not found: ' + task_id)
            task = dict(tasks[task_id])
            task.update({key: value for key, value in arguments.items() if key != 'task_id'})
        tasks[task_id] = task
        operations[operation_id] = dict(tool=tool, arguments=arguments, result=dict(task))
        store.write(state)  # Task and operation record are persisted together.
        return dict(task, idempotent=False)


def create_study_task(title, due_date, source_ids, operation_id, store):
    arguments = dict(title=title.strip(), due_date=due_date, source_ids=sorted(set(source_ids)))
    return _write_task('create_study_task', arguments, operation_id, store)


def update_study_task(task_id, operation_id, store, title=None, due_date=None, source_ids=None, status=None):
    arguments = dict(task_id=task_id)
    if title is not None:
        arguments['title'] = title.strip()
    if due_date is not None:
        arguments['due_date'] = due_date
    if source_ids is not None:
        arguments['source_ids'] = sorted(set(source_ids))
    if status is not None:
        arguments['status'] = status
    return _write_task('update_study_task', arguments, operation_id, store)


def get_study_task(task_id, store):
    """P2-03: 读取真实存储状态."""
    task = store.read().get("tasks", {}).get(task_id)
    if task is None:
        raise ValueError("study task not found: {!r}".format(task_id))
    return dict(task)


def dispatch_calls(calls, registry, **context):
    """P2-04: 处理多个工具请求，保持每个调用 ID 和结果关联."""
    results = []
    for position, call in enumerate(calls or []):
        call_id = call.get("call_id", "call-{}".format(position + 1))
        name = call.get("name", "")
        arguments = call.get("arguments") or {}
        try:
            validate_arguments(name, arguments, context.get("corpus", []))
            function = registry[name]
            journal = context.get('journal')
            result = journal.execute(name, arguments, call_id, function) if journal else function(**arguments)
            results.append({"call_id": call_id, "name": name, "result": result})
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            results.append({"call_id": call_id, "name": name,
                            "result": {"error": str(error)}})
    return results


def run(payload, **context):
    """Default: execute tools in a separate MCP server; local mode is a baseline."""
    context = dict(context, run_id=context.get('run_id') or str(uuid4()))
    payload = {key: value for key, value in payload.items() if key not in ('request_id', 'operation_id', 'run_id')}
    transport = payload.get("transport", context.get("config", {}).get("tool_transport", "mcp"))
    if transport == "local":
        return _run_loop(payload, **context)
    if transport != "mcp":
        raise ValueError("transport must be local or mcp")
    return asyncio.run(_run_mcp(payload, **context))


async def _run_mcp(payload, **context):
    from p2_function_calling.practice.mcp_client import connect
    from practice_common.runtime import save_json
    artifact_dir = Path(context.get("artifact_dir", "."))
    artifact_dir.mkdir(parents=True, exist_ok=True)
    # Export the supplied corpus so local and remote modes use identical data.
    corpus_path = artifact_dir / "mcp-corpus.jsonl"
    corpus_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                  for row in context.get("corpus", [])), encoding="utf-8")
    timeout = int(os.environ.get("MCP_DEBUG_TIMEOUT_SECONDS",
                                 context.get("config", {}).get("timeout_seconds", 30)))
    async with connect(artifact_dir / "study_tasks.json", corpus_path,
                       timeout=timeout, trace=context.get("trace")) as client:
        catalog = await client.session.read_resource("course://catalog")
        client.record("resources/read", uri="course://catalog")
        save_json(artifact_dir / "mcp-tools.json", client.schemas)
        loop = asyncio.get_running_loop()

        def remote_tool(name):
            def call(**arguments):
                future = asyncio.run_coroutine_threadsafe(client.call_tool(name, arguments), loop)
                try:
                    return future.result(timeout=timeout + 1)
                except TimeoutError:
                    future.cancel()
                    raise RuntimeError("mcp_tool_timeout")
            return call

        registry = {schema["function"]["name"]: remote_tool(schema["function"]["name"])
                    for schema in client.schemas}
        remote_context = dict(context, registry=registry, tool_schemas=model_schemas(client.schemas),
                              course_catalog=catalog.contents[0].text)
        result = await asyncio.to_thread(_run_loop, payload, **remote_context)
        result["transport"] = "mcp"
        return result


def _run_loop(payload, **context):
    """P2-05: 实现原生工具调用闭环、错误恢复与调用预算."""
    model = context.get("model")
    if model is None:
        return _result("error", "缺少模型，无法运行工具调用。", [], model_calls=0, tool_calls=0)
    config = context.get("config", {})
    max_rounds = int(config.get("max_rounds", 8))
    max_model_calls = int(config.get("max_model_calls", max_rounds))
    artifact_dir = Path(context.get("artifact_dir", "."))
    store = JsonStore(artifact_dir / "study_tasks.json")
    corpus = context.get("corpus", [])
    registry = {
        "search_notes": lambda query: {"evidence": search_notes(query, corpus)},
        "read_note": lambda doc_id, paragraph_id: {"evidence": [
            read_note(doc_id, paragraph_id, corpus)]},
        "create_study_task": lambda title, due_date, source_ids, operation_id:
            create_study_task(title, due_date, source_ids, operation_id, store),
        "update_study_task": lambda task_id, operation_id, **fields:
            update_study_task(task_id, operation_id, store, **fields),
        "get_study_task": lambda task_id: get_study_task(task_id, store),
    }
    registry = context.get("registry", registry)
    tools = context.get("tool_schemas", list(registry))
    messages = [{"role": "system", "content": "先获取真实证据，再创建和读回任务。日期不得自行编造。source_ids 只接受文档 ID（例如 p2-note），不接受段落拼接 ID。修改已有任务用 update_study_task；写入重试由 host 管理，不要自行重复创建。"},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    if context.get("course_catalog"):
        messages[0]["content"] += " 可用资料：" + context["course_catalog"]
    journal = OperationJournal(artifact_dir / 'write_operations.json', context['run_id'],
                               retries=int(config.get('write_retries', 1)), trace=context.get('trace'))
    if payload.get('resume_operation_id'):
        recovered = journal.resume(payload['resume_operation_id'], registry)
        return dict(status='completed', run_id=context['run_id'], recovered_operation=recovered)
    citations = []
    write_state = 'not_requested'
    model_calls = 0
    tool_calls = 0
    trace = context.get("trace")
    for round_number in range(max_rounds):
        if model_calls >= max_model_calls:
            return _result("budget_exhausted", "模型调用预算耗尽。", citations,
                           model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model))
        try:
            response = model.respond(messages, tools=tools)
            model_calls += 1
        except RuntimeError as error:
            return _result("budget_exhausted", str(error), citations,
                           model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model))
        _emit(trace, "model_response", round=round_number + 1, response=response)
        if response.get("type") == "final":
            final_status = 'failed' if write_state == 'failed' else 'outcome_unknown' if write_state == 'outcome_unknown' else 'completed'
            final = _result(final_status, response.get("answer", ""), citations,
                           model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model))
            final.update(run_id=context['run_id'], write_status=write_state)
            return final
        if response.get("type") == "tool_call":
            calls = [response]
        elif response.get("type") == "tool_calls":
            calls = response.get("calls", [])
        else:
            return _result("invalid_action", "模型返回了无法识别的动作。", citations,
                           model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model))
        observations = dispatch_calls(calls, registry, corpus=corpus, journal=journal)
        tool_calls += len(observations)
        messages.append({"role": "assistant", "content": response})
        for observation in observations:
            result = observation["result"]
            if observation['name'] in WRITE_TOOLS:
                if 'error' in result:
                    write_state = 'outcome_unknown' if 'outcome unknown' in result['error'] else 'failed'
                else:
                    write_state = 'succeeded'
            for evidence in result.get("evidence", []) if isinstance(result, dict) else []:
                citation = {"doc_id": evidence.get("doc_id"),
                            "paragraph_id": evidence.get("paragraph_id")}
                if citation not in citations:
                    citations.append(citation)
            messages.append({"role": "tool", "call_id": observation["call_id"],
                             "content": json.dumps(result, ensure_ascii=False)})
            _emit(trace, "tool_result", **observation)
        if write_state == 'outcome_unknown':
            pending = [record for record in journal.store.read().get('operations', {}).values()
                       if record['run_id'] == context['run_id'] and record['status'] == 'outcome_unknown']
            return dict(status='outcome_unknown', answer='写入结果未知，已停止后续操作。请恢复保存的 operation_id。',
                        run_id=context['run_id'], operations=pending, citations=citations,
                        metrics=dict(model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model)))
    return _result("max_rounds", "达到最大轮数，未能完成任务。", citations,
                   model_calls=model_calls, tool_calls=tool_calls, usage=_usage(model))


def _result(status, answer, citations, **metrics):
    return {"status": status, "answer": answer, "citations": citations, "metrics": metrics}


def _usage(model):
    return dict(getattr(model, "total_usage", {}) or {})


def _emit(trace, event, **fields):
    if trace is not None:
        trace.emit(event, **fields)
