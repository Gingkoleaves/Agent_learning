"""LangGraph study planner with durable confirmation and idempotent saving."""
import asyncio
import json
import time
from datetime import date, timedelta
from pathlib import Path
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from p1_basic_concepts.practice.solution import search_notes
from p2_function_calling.practice.solution import create_study_task, get_study_task
from practice_common.runtime import JsonStore
from .state import StudyState, initial_state, transition

PROMPT = '''根据 question、profile、start_date 和 search_notes 实际返回的证据生成三天计划。
检索已经完成。仅输出 JSON 对象 {"title":字符串,"days":[{"date":"YYYY-MM-DD",
"minutes":正整数,"activity":具体学习动作,"citations":[{"doc_id":字符串,"paragraph_id":字符串}]}]}。
days 必须从 start_date 起连续三天，每天 minutes 不超过 profile.minutes_per_day。
每天引用返回的证据，不伪造来源。已学内容用于复习，未学内容用于学习。不要保存任务。'''


def emit(context, event, **fields):
    if context.get('trace'):
        context['trace'].emit(event, **fields)


def parse_plan(response):
    value = response.get('plan', response.get('answer', ''))
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value.strip().removeprefix('```json').removesuffix('```').strip())
    except (ValueError, AttributeError):
        return None


def validate_plan(plan, state):
    errors = []
    if not isinstance(plan, dict) or not isinstance(plan.get('title'), str) or not plan['title'].strip():
        return ['plan.title is required']
    days = plan.get('days')
    if not isinstance(days, list) or len(days) != 3:
        return ['exactly three days required']
    known = {(str(e['doc_id']), str(e['paragraph_id'])) for e in state['evidence']}
    for index, day in enumerate(days):
        if not isinstance(day, dict):
            errors.append('day must be object')
            continue
        if day.get('date') != (date.fromisoformat(state['start_date']) + timedelta(days=index)).isoformat():
            errors.append('dates must be consecutive from start_date')
        minutes = day.get('minutes')
        if type(minutes) is not int or not 0 < minutes <= state['profile']['minutes_per_day']:
            errors.append('daily time budget exceeded or invalid')
        if not isinstance(day.get('activity'), str) or not day['activity'].strip():
            errors.append('activity required')
        citations = day.get('citations')
        if not isinstance(citations, list) or not citations or any(
            not isinstance(c, dict) or (str(c.get('doc_id')), str(c.get('paragraph_id'))) not in known
            for c in citations):
            errors.append('missing or fabricated citation')
    return sorted(set(errors))


def prompt_messages(state):
    call = dict(type='tool_call', call_id='retrieval-' + state['session_id'],
                name='search_notes', arguments={'query': state['query']})
    return [dict(role='system', content=PROMPT),
        dict(role='user', content=json.dumps({k: state[k] for k in
             ('question', 'query', 'profile', 'start_date')}, ensure_ascii=False)),
        dict(role='assistant', content=call),
        dict(role='tool', tool_call_id=call['call_id'],
             content=json.dumps({'evidence': state['evidence']}, ensure_ascii=False)),
        dict(role='user', content='校验反馈：' + json.dumps(state['validation_errors'], ensure_ascii=False))]


class Nodes:
    def __init__(self, context):
        self.context = context
        self.config = context.get('config', {})
        self.store = JsonStore(Path(context['artifact_dir']) / 'study_tasks.json')

    def call_count(self, state):
        journal = JsonStore(Path(self.context['artifact_dir']) / 'model_calls.json')
        return max(state['metrics']['model_calls'], journal.read().get(state['session_id'], 0))

    def reserve_call(self, state, count):
        # Single-writer CLI, just like the reused P2 JsonStore. Commit BEFORE I/O.
        journal = JsonStore(Path(self.context['artifact_dir']) / 'model_calls.json')
        counts = journal.read()
        counts[state['session_id']] = count
        journal.write(counts)

    async def load_profile(self, state):
        profile = dict(state['profile'])
        if type(profile.get('minutes_per_day')) is not int or profile['minutes_per_day'] <= 0:
            raise ValueError('profile.minutes_per_day must be positive integer')
        date.fromisoformat(state['start_date'])
        return transition(state, 'loaded', profile=profile)

    async def retrieve(self, state):
        evidence = search_notes(state['query'], self.context.get('corpus', []))[:3]
        evidence = [{k: e[k] for k in ('doc_id', 'paragraph_id', 'text')} for e in evidence]
        for e in evidence:
            e['text'] = e['text'][:450]
        metrics = dict(state['metrics'], tool_calls=state['metrics']['tool_calls'] + 1)
        emit(self.context, 'tool_result', call_id='retrieval-' + state['session_id'],
             name='search_notes', arguments={'query': state['query']}, result=evidence)
        return transition(state, 'retrieved' if evidence else 'no_evidence', evidence=evidence, metrics=metrics)

    async def generate(self, state):
        metrics = dict(state['metrics'])
        metrics['model_calls'] = self.call_count(state)
        if metrics['model_calls'] >= min(self.config.get('max_model_calls', 8), self.config.get('max_rounds', 8)):
            return transition(state, 'budget_exhausted', metrics=metrics)
        messages = prompt_messages(state)
        estimate = len(json.dumps(messages, ensure_ascii=False))
        if estimate + self.config.get('reserve_output_tokens', 500) > self.config.get('context_token_budget', 4000):
            return transition(state, 'context_exhausted')
        metrics['peak_input_tokens_estimate'] = max(metrics['peak_input_tokens_estimate'], estimate)
        metrics['model_calls'] += 1
        self.reserve_call(state, metrics['model_calls'])
        try:
            response = await self.context['model'].arespond(messages)
        except (RuntimeError, ValueError) as error:
            return transition(state, 'model_error', validation_errors=[str(error)], metrics=metrics)
        usage = response.get('usage') or {}
        totals = dict(metrics['usage'])
        for k, v in usage.items():
            if isinstance(v, (int, float)):
                totals[k] = totals.get(k, 0) + v
        metrics['usage'] = totals
        if usage:
            metrics['usage_kind'] = 'provider'
        emit(self.context, 'model_result', session_id=state['session_id'], response=response, metrics=metrics)
        return transition(state, 'generated', candidate_plan=parse_plan(response), metrics=metrics)

    async def validate(self, state):
        errors = validate_plan(state['candidate_plan'], state)
        status = 'waiting_confirmation' if not errors else ('retry' if state['revision_count'] < 2 else 'validation_failed')
        emit(self.context, 'validation', errors=errors, revision=state['revision_count'])
        return transition(state, status, validation_errors=errors,
                          revision_count=state['revision_count'] + (status == 'retry'))

    async def confirm(self, state):
        decision = interrupt({'kind': 'confirmation', 'plan': state['candidate_plan']})
        if type(decision) is not bool:
            raise ValueError('decision must be a JSON boolean')
        return transition(state, 'approved' if decision else 'rejected', user_decision=decision)

    async def save(self, state):
        if state['user_decision'] is not True:
            raise ValueError('explicit confirmation required')
        plan = state['candidate_plan']
        result = create_study_task(title=json.dumps(plan, ensure_ascii=False, sort_keys=True),
            due_date=plan['days'][-1]['date'],
            source_ids=[c['doc_id'] for d in plan['days'] for c in d['citations']],
            operation_id=state['request_id'], store=self.store)
        emit(self.context, 'external_write', request_id=state['request_id'], result=result)
        persisted = get_study_task(result['task_id'], self.store)
        return transition(state, 'saved', saved_task_id=persisted['task_id'],
            metrics=dict(state['metrics'], tool_calls=state['metrics']['tool_calls'] + 2))

    async def finish(self, state):
        return transition(state, 'completed')


def build_graph(**context):
    nodes = context.get('nodes_class', Nodes)(context)
    graph = StateGraph(StudyState)
    for name in ('load_profile', 'retrieve', 'generate', 'validate', 'confirm', 'save', 'finish'):
        graph.add_node(name, getattr(nodes, name))
    graph.add_edge(START, 'load_profile')
    graph.add_edge('load_profile', 'retrieve')
    graph.add_conditional_edges('retrieve', lambda s: 'generate' if s['status'] == 'retrieved' else END)
    graph.add_conditional_edges('generate', lambda s: 'validate' if s['status'] == 'generated' else END)
    graph.add_conditional_edges('validate', lambda s: {'retry': 'generate', 'waiting_confirmation': 'confirm'}.get(s['status'], END))
    graph.add_conditional_edges('confirm', lambda s: 'save' if s['user_decision'] is True else END)
    graph.add_edge('save', 'finish')
    graph.add_edge('finish', END)
    return graph.compile(checkpointer=context.get('checkpointer'),
        interrupt_after={'retrieval': ['retrieve'], 'save': ['save']}.get(context.get('stop_after')))


def result_of(state, started, mode):
    return dict(state, mode=mode, metrics=dict(state['metrics'], elapsed_seconds=time.monotonic() - started))


async def _graph_run(payload, context):
    started = time.monotonic()
    root = Path(context['artifact_dir'])
    root.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(root / 'checkpoints.sqlite')) as saver:
        graph = build_graph(**dict(context, checkpointer=saver, stop_after=payload.get('stop_after')))
        state = initial_state(payload)
        cfg = {'configurable': {'thread_id': state['session_id']}, 'recursion_limit': 32}
        if context.get('callbacks'):
            cfg['callbacks'] = context['callbacks']
        snapshot = await graph.aget_state(cfg)
        if payload.get('resume'):
            if not snapshot.values:
                return {'status': 'session_not_found', 'session_id': state['session_id']}
            state = snapshot.values
            decision = payload.get('decision')
            emit(context, 'resume_session', session_id=state['session_id'], decision=decision, next=list(snapshot.next))
            if decision is not None and type(decision) is not bool:
                return dict(state, status='invalid_decision')
            waiting = any(task.interrupts for task in snapshot.tasks)
            if not snapshot.next or (waiting and decision is None):
                return result_of(state, started, 'langgraph')
            if decision is not None and not waiting:
                return dict(state, status='decision_not_requested')
            arg = Command(resume=decision) if waiting else None
        else:
            if snapshot.values:
                return dict(snapshot.values, status='session_exists')
            emit(context, 'new_session', session_id=state['session_id'])
            arg = state
        try:
            # Approval/request ID must reach disk before the external write starts.
            await asyncio.wait_for(graph.ainvoke(arg, cfg, durability='sync'), context.get('config', {}).get('timeout_seconds', 30))
        except TimeoutError:
            snapshot = await graph.aget_state(cfg)
            latest = snapshot.values or state
            return dict(latest, status='timeout', metrics=dict(latest['metrics'],
                model_calls=Nodes(context).call_count(latest), elapsed_seconds=time.monotonic() - started))
        snapshot = await graph.aget_state(cfg)
        return result_of(snapshot.values, started, 'langgraph')


def run_agents_sdk(payload, **context):
    """P5-03: run an Agent with a retrieval tool and validate its final plan."""
    from .agents_sdk import execute
    context.setdefault('artifact_dir', Path(__file__).parent / 'artifacts')
    return asyncio.run(execute(payload, context))


def run(payload, **context):
    context.setdefault('artifact_dir', Path(__file__).parent / 'artifacts')
    if payload.get('mode') == 'agents_sdk':
        return run_agents_sdk(payload, **context)
    if payload.get('mode', 'langgraph') != 'langgraph':
        raise ValueError('mode must be langgraph or agents_sdk')
    result = asyncio.run(_graph_run(payload, context))
    if result['status'] != 'waiting_confirmation':
        return result

    print(f"\n会话：{result['session_id']}")
    print(json.dumps(result['candidate_plan'], ensure_ascii=False, indent=2))
    while True:
        answer = input('是否确认保存该计划？[y/n]：').strip().lower()
        if answer in ('y', 'n'):
            break
        print('请输入 y（保存）或 n（拒绝）。')

    return asyncio.run(_graph_run({
        'session_id': result['session_id'],
        'resume': True,
        'decision': answer == 'y',
    }, context))
