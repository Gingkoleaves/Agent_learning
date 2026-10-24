"""Repeatable evaluations with independent environments and fail-closed grading."""
import asyncio
import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from practice_common.runtime import ROOT, JsonStore, load_json, load_jsonl, save_json

HERE = Path(__file__).parent
CATEGORIES = {'knowledge', 'comparison', 'memory', 'fault', 'plan'}


def validate_case(case):
    if case.get('fixture_only') is not False or case.get('annotation_status') != 'complete':
        raise ValueError('unannotated fixture cannot be evaluated: ' + str(case.get('id')))
    required = {'id', 'category', 'input', 'initial_state', 'expected_final_state', 'expected_facts',
                'expected_evidence_ids', 'allowed_actions', 'required_actions', 'forbidden_actions',
                'user_script', 'expected_status', 'rules', 'rubric'}
    if required - case.keys() or case.get('expected_final_state') is None:
        raise ValueError('incomplete annotations: ' + str(case.get('id')))
    if not re.fullmatch(r'[A-Za-z0-9_-]+', case['id']) or case['category'] not in CATEGORIES:
        raise ValueError('invalid case id/category')
    if set(case['required_actions']) - set(case['allowed_actions']):
        raise ValueError('required action is not allowed')
    if set(case['allowed_actions']) & set(case['forbidden_actions']):
        raise ValueError('conflicting action annotations')
    if not case['rubric'] or not case['expected_status']:
        raise ValueError('empty rubric/status')


def reset_environment(initial_state, **context):
    """P6-01: create fresh storage; never reuse a previous trial's checkpoint."""
    root = Path(context.get('artifact_dir', HERE / 'artifacts' / uuid4().hex))
    root.mkdir(parents=True, exist_ok=False)
    state = deepcopy(initial_state)
    save_json(root / 'study_tasks.json', state.get('study_tasks', {'tasks': {}, 'operations': {}}))
    save_json(root / 'profiles.json', state.get('profiles', {'users': {}}))
    save_json(root / 'initial_state.json', state)
    return {'artifact_dir': root, 'session_id': str(uuid4())}


def snapshot(root):
    """Read disk, not a model's claimed result. Normalize only nondeterministic IDs/times."""
    database = JsonStore(Path(root) / 'study_tasks.json').read()
    profiles = JsonStore(Path(root) / 'profiles.json').read()
    tasks = []
    for task_id, item in sorted(database.get('tasks', {}).items()):
        task = dict(item, task_id=task_id)
        try:
            task['plan'] = json.loads(task['title'])
        except (ValueError, KeyError, TypeError):
            pass
        tasks.append(task)
    return dict(task_count=len(tasks), tasks=tasks, operation_count=len(database.get('operations', {})),
                profiles={user: {key: item['value'] for key, item in value.get('facts', {}).items()}
                          for user, value in profiles.get('users', {}).items()})


def _matches(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _matches(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(_matches(e, a) for e, a in zip(expected, actual))
    return type(expected) is type(actual) and expected == actual


def evidence_id(value):
    return str(value.get('doc_id', '')) + ':' + str(value.get('paragraph_id', ''))


def evaluate_case(case, actual, final_state, *, corpus=None):
    """P6-02: mechanical checks + explicit semantic review, never trust save text."""
    validate_case(case)
    corpus = load_jsonl(ROOT / 'data/corpus.jsonl') if corpus is None else corpus
    sources = {evidence_id(row): row['text'] for row in corpus}
    checks, detail = {}, {}
    structural = (isinstance(actual, dict) and isinstance(actual.get('answer'), str)
                  and isinstance(actual.get('citations'), list)
                  and all(isinstance(c, dict) for c in actual.get('citations', []))
                  and isinstance(actual.get('claims', []), list)
                  and all(isinstance(c, dict) for c in actual.get('claims', [])))
    checks['structure'] = structural
    if not structural:
        return dict(success=False, checks=checks, details={'structure': 'malformed output'}, semantic_review='not_reached')
    citations = {evidence_id(c) for c in actual['citations']}
    observed = set(actual.get('_observed_evidence_ids', []))
    checks['status'] = actual.get('status') in case['expected_status']
    checks['citation_exists'] = citations <= sources.keys()
    checks['citation_observed'] = citations <= observed
    checks['expected_evidence'] = set(case['expected_evidence_ids']) <= citations
    claims = actual.get('claims', [])
    checks['quotes'] = all(isinstance(c.get('quote'), str) and bool(c['quote'])
        and c['quote'] in sources.get(evidence_id(c), '') and evidence_id(c) in citations
        and isinstance(c.get('text'), str) and bool(c['text']) for c in claims)
    facts = []
    for fact in case['expected_facts']:
        matching = [c for c in claims if evidence_id(c) in fact['evidence_ids']]
        facts.append(all(any(term.casefold() in c['quote'].casefold() and term.casefold() in c['text'].casefold()
                             for c in matching) for term in fact['contains']))
    checks['facts'] = all(facts)
    detail['facts'] = dict(zip([f['id'] for f in case['expected_facts']], facts))
    # Extractive outputs have a checkable support relation. Free paraphrases still
    # need a human reviewer, even when all keywords and source IDs are present.
    extractive = all(c.get('text') == c.get('quote') for c in claims)
    if claims:
        extractive = extractive and actual['answer'] == '\n\n'.join(c['text'] for c in claims)
    checks['citation_support'] = extractive
    checks['claim_coverage'] = (not case['expected_facts'] or bool(claims))
    if case['expected_status'] == ['no_evidence']:
        checks['no_evidence_response'] = (not citations and not claims and any(
            phrase in actual['answer'] for phrase in ('没有依据', '证据不足', '未找到', '没有证据', '无法回答')))
    events = actual.get('_events', [])
    actions = [e['name'] for e in events if e['event'] in ('tool_start', 'forbidden_action')]
    checks['allowed_actions'] = set(actions) <= set(case['allowed_actions'])
    checks['forbidden_actions'] = not (set(actions) & set(case['forbidden_actions']))
    checks['required_actions'] = set(case['required_actions']) <= set(actions)
    checks['final_state'] = _matches(case['expected_final_state'], final_state)
    detail['expected_final_state'] = case['expected_final_state']
    detail['actual_final_state'] = final_state
    approved = False
    safe = True
    for event in events:
        if event['event'] == 'confirmation':
            approved = event['decision'] is True
        if event['event'] == 'tool_start' and event['name'] in ('create_study_task', 'update_study_task'):
            safe = safe and approved
    rules = {'no_fabrication': checks['citation_exists'] and checks['citation_observed'] and checks['quotes']}
    if 'confirmation' in case['rules']:
        rules['confirmation'] = safe
    if actual.get('claimed_saved'):
        rules['truthful_save'] = any(t['task_id'] == actual.get('saved_task_id')
            and t.get('plan') == actual.get('candidate_plan') for t in final_state['tasks'])
    if 'idempotency' in case['rules']:
        rules['idempotency'] = final_state['task_count'] == case['expected_final_state']['task_count'] and (
            final_state['operation_count'] == case['expected_final_state']['operation_count'])
    if 'latest_preference' in case['rules']:
        latest = final_state['profiles'].get(case['input'].get('user_id', 'learner'), {}).get('minutes_per_day')
        days = actual.get('candidate_plan', {}).get('days', [])
        rules['latest_preference'] = bool(days) and all(type(d.get('minutes')) is int and 0 < d['minutes'] <= latest for d in days)
    checks['rules'] = all(rules.values())
    detail['rules'] = rules
    if case['input']['kind'] in ('plan', 'memory'):
        from p5_agent_framework.practice.solution import validate_plan
        checks['plan_constraints'] = False
        if actual.get('candidate_plan'):
            plan_state = dict(evidence=actual.get('evidence', []), profile=actual['profile'], start_date=case['input']['start_date'])
            checks['plan_constraints'] = not validate_plan(actual['candidate_plan'], plan_state)
    return dict(success=all(checks.values()), checks=checks, details=detail,
                semantic_review='extractive_mechanical_only' if extractive else 'human_review_required')


def _percentile(values, percentile):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * percentile
    lo, hi = math.floor(index), math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def summarize(results):
    """P6-03: all-three is defined only for exactly trials {1,2,3}."""
    groups = defaultdict(list)
    for row in results:
        groups[row['case_id']].append(row)
    if any(len({r['trial'] for r in rows}) != len(rows) for rows in groups.values()):
        raise ValueError('duplicate trial in summary')
    complete = [rows for rows in groups.values() if len(rows) == 3 and {r['trial'] for r in rows} == {1, 2, 3}]
    n = len(results)
    rules = defaultdict(lambda: {'covered_runs': 0, 'violations': 0})
    for row in results:
        for name, ok in row.get('details', {}).get('rules', {}).items():
            rules[name]['covered_runs'] += 1
            rules[name]['violations'] += int(not ok)
    usage = Counter()
    for row in results:
        usage.update(row.get('usage', {}))
    citation_rows = [r for r in results if r.get('actual', {}).get('citations')]
    return dict(runs=n, cases=len(groups), successes=sum(r['success'] for r in results),
        single_success_rate=sum(r['success'] for r in results) / n if n else None,
        all_three_success_rate=sum(all(r['success'] for r in rows) for rows in complete) / len(complete) if complete else None,
        complete_three_trial_cases=len(complete), incomplete_three_trial_cases=len(groups) - len(complete),
        mean_model_calls=sum(r['model_calls'] for r in results) / n if n else None,
        mean_tool_calls=sum(r['tool_calls'] for r in results) / n if n else None,
        p50_seconds=_percentile([r['duration_seconds'] for r in results], .50),
        p95_seconds=_percentile([r['duration_seconds'] for r in results], .95),
        usage=dict(usage), usage_kind='provider' if usage else 'unavailable',
        citation_runs=len(citation_rows),
        citation_valid_rate=sum(r['checks'].get('citation_exists', False) and r['checks'].get('citation_observed', False)
                                and r['checks'].get('quotes', False) for r in citation_rows) / len(citation_rows) if citation_rows else None,
        human_review_required=sum(r.get('semantic_review') == 'human_review_required' for r in results),
        rules=dict(rules), by_category={category: {'runs': len(rows), 'successes': sum(r['success'] for r in rows)}
            for category in sorted({r['category'] for r in results})
            for rows in [[r for r in results if r['category'] == category]]})


def configure_observability(**context):
    """P6-04: a dedicated provider; no global provider mutations across runs."""
    from .observability import Observability
    return Observability(context.get('artifact_dir', HERE / 'artifacts'), context.get('langsmith', False))


def _new_model(context):
    from .offline import OfflineModel
    from practice_common.model_adapter import DeepSeekAdapter
    original = context.get('model')
    if original is None:
        return OfflineModel()
    if isinstance(original, DeepSeekAdapter):
        return DeepSeekAdapter(api_key=original.api_key, model_name=original.model_name,
            max_calls=original.max_calls, timeout_seconds=original.timeout_seconds,
            base_url=original.base_url, max_output_tokens=original.max_output_tokens)
    return deepcopy(original)


async def _trial(case, trial, variant, suite, root, obs, context):
    from .agent import execute
    from .observability import Recorder, ObservedModel
    folder = root / suite / variant / case['id'] / f'trial-{trial}'
    environment = reset_environment(case['initial_state'], artifact_dir=folder)
    recorder = Recorder(folder / 'trace.jsonl', obs, context['config']['max_tool_calls'])
    model = ObservedModel(_new_model(context), recorder, context['config']['max_model_calls'])
    request = {key: deepcopy(case.get(key, {} if key == 'faults' else [])) for key in ('input', 'user_script', 'faults')}
    started = time.perf_counter()
    with obs.span('task', case_id=case['id'], trial=trial, suite=suite, variant=variant) as task_span:
        try:
            actual = await asyncio.wait_for(execute(request, root=environment['artifact_dir'], corpus=context['corpus'],
                recorder=recorder, model=model, config=context['config'], variant=variant),
                timeout=context['config']['timeout_seconds'])
        except Exception as error:
            recorder.emit('task_error', error_type=type(error).__name__, error=str(error))
            actual = {'status': 'timeout' if isinstance(error, TimeoutError) else 'error',
                      'answer': '', 'citations': [], 'error': str(error)}
        duration = time.perf_counter() - started
        final_state = snapshot(folder)
        actual['_events'] = recorder.events
        observed = set()
        for event in recorder.events:
            if event['event'] == 'tool_end' and event['name'] in ('search_notes', 'read_note'):
                result = event['result']
                for item in result if isinstance(result, list) else [result]:
                    observed.add(evidence_id(item))
        actual['_observed_evidence_ids'] = sorted(observed)
        graded = evaluate_case(case, actual, final_state, corpus=context['corpus'])
        task_span.set_attribute('success', graded['success'])
        trace_id = format(task_span.get_span_context().trace_id, '032x')
        public_actual = {k: v for k, v in actual.items() if not k.startswith('_')}
        save_json(folder / 'actual.json', public_actual)
        save_json(folder / 'final_state.json', final_state)
        record = dict(case_id=case['id'], category=case['category'], trial=trial, variant=variant, suite=suite,
            **graded, duration_seconds=duration, model_calls=model.calls, tool_calls=recorder.tool_calls,
            model=model.model_name, usage=model.usage, trace_id=trace_id,
            trace_path=str((folder / 'trace.jsonl').relative_to(root)), actual=public_actual, final_state=final_state)
        return record


def _load_suite(path, expected_count, category_counts=False):
    cases = load_jsonl(path)
    if len(cases) != expected_count or len({c['id'] for c in cases}) != len(cases):
        raise ValueError(f'{path}: expected {expected_count} uniquely identified cases')
    for case in cases:
        validate_case(case)
    if category_counts and Counter(c['category'] for c in cases) != Counter({k: 6 for k in CATEGORIES}):
        raise ValueError('development must contain five categories of six cases')
    return cases


def run(payload, **context):
    """P6-05: default development comparison; holdout is a separate explicit run."""
    suite = payload.get('suite', 'development')
    if suite not in ('development', 'holdout') or payload.get('agent_chapter', 5) != 5:
        raise ValueError('supported suite: development/holdout; agent_chapter must be 5')
    repeats = payload.get('repeats', 1 if suite == 'holdout' else 3)
    if type(repeats) is not int or repeats != (1 if suite == 'holdout' else 3):
        raise ValueError('development requires 3 trials; holdout exactly 1')
    variants = payload.get('variants', ['fixed'] if suite == 'holdout' else ['baseline', 'fixed'])
    if not variants or len(set(variants)) != len(variants) or set(variants) - {'baseline', 'fixed'}:
        raise ValueError('invalid variants')
    if suite == 'holdout' and variants != ['fixed']:
        raise ValueError('holdout runs only the frozen fixed variant')
    context = dict(context)
    context['config'] = dict(load_json(HERE / 'config.json'), **context.get('config', {}))
    context.setdefault('corpus', load_jsonl(ROOT / 'data/corpus.jsonl'))
    development = _load_suite(HERE / 'data/cases.jsonl', 30, True)
    cases = development if suite == 'development' else _load_suite(HERE / 'data/holdout.jsonl', 6)
    if suite == 'holdout':
        development_inputs = {json.dumps(c['input'], sort_keys=True) for c in development}
        if {c['id'] for c in development} & {c['id'] for c in cases} or any(json.dumps(c['input'], sort_keys=True) in development_inputs for c in cases):
            raise ValueError('holdout overlaps development')
    root = Path(context.get('artifact_dir', HERE / 'artifacts')) / ('evaluation-' + uuid4().hex)
    root.mkdir(parents=True)
    obs = configure_observability(artifact_dir=root, langsmith=payload.get('langsmith_sample', False))
    result_path = root / 'results.jsonl'
    results = []
    try:
        for variant in variants:
            for case in cases:
                for trial in range(1, repeats + 1):
                    record = asyncio.run(_trial(case, trial, variant, suite, root, obs, context))
                    results.append(record)
                    with result_path.open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
    finally:
        obs.close()
    summary = {variant: summarize([r for r in results if r['variant'] == variant]) for variant in variants}
    manifest = dict(suite=suite, repeats=repeats, config=context['config'], variants=variants,
        dataset_sha256=hashlib.sha256(json.dumps(cases, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        corpus_sha256=hashlib.sha256(json.dumps(context['corpus'], sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        semantic_scope='Mechanical/extractive checks; free-form answer correctness requires human review.',
        langsmith=obs.langsmith)
    import importlib.metadata
    import platform
    manifest['python_version'] = platform.python_version()
    manifest['dependencies'] = {name: importlib.metadata.version(name) for name in
        ('langgraph', 'langgraph-checkpoint-sqlite', 'opentelemetry-sdk', 'langsmith', 'httpx')}
    manifest['implementation_sha256'] = hashlib.sha256(b''.join(
        p.name.encode() + p.read_bytes() for p in sorted(HERE.glob('*.py')))).hexdigest()
    save_json(root / 'manifest.json', manifest)
    save_json(root / 'summary.json', summary)
    review = [{'case_id': r['case_id'], 'trial': r['trial'], 'variant': r['variant'], 'trace_path': r['trace_path'],
               'answer': r['actual']['answer'], 'rubric': next(c['rubric'] for c in cases if c['id'] == r['case_id']),
               'reviewer': None, 'semantic_correct': None, 'notes': ''} for r in results]
    save_json(root / 'human_review.json', review)
    return dict(status='completed', suite=suite, summary=summary, langsmith=obs.langsmith,
                artifact_dir=str(root), results_path=str(result_path), human_review_path=str(root / 'human_review.json'))
