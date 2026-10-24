"""Single-writer fields use replacement reducers, including lists on replay."""
from typing import Any, TypedDict
from uuid import uuid4

class StudyState(TypedDict):
    session_id: str
    question: str
    query: str
    profile: dict[str, Any]
    start_date: str
    evidence: list[dict[str, Any]]
    candidate_plan: dict[str, Any] | None
    validation_errors: list[str]
    user_decision: bool | None
    request_id: str
    saved_task_id: str | None
    revision_count: int
    status: str
    metrics: dict[str, Any]


def initial_state(payload):
    return StudyState(session_id=payload.get('session_id') or str(uuid4()),
        question=payload.get('question', '生成三天学习计划'),
        query=payload.get('query', payload.get('question', 'ReAct')),
        profile=payload.get('profile', {'minutes_per_day': 45, 'completed': []}),
        start_date=payload.get('start_date', '2026-10-23'), evidence=[],
        candidate_plan=None, validation_errors=[], user_decision=None,
        request_id=str(uuid4()), saved_task_id=None, revision_count=0,
        status='new', metrics={'model_calls': 0, 'tool_calls': 0, 'usage': {},
        'usage_kind': 'unavailable', 'peak_input_tokens_estimate': 0})

ALLOWED = {
    'new': {'loaded'}, 'loaded': {'retrieved', 'no_evidence'},
    'retrieved': {'generated', 'budget_exhausted', 'context_exhausted', 'model_error'},
    'generated': {'retry', 'waiting_confirmation', 'validation_failed'},
    'retry': {'generated', 'budget_exhausted', 'context_exhausted', 'model_error'},
    'waiting_confirmation': {'approved', 'rejected'},
    'approved': {'saved'}, 'saved': {'completed'},
}


def transition(state, status, **updates):
    if status not in ALLOWED.get(state['status'], set()):
        raise ValueError(f"illegal transition: {state['status']} -> {status}")
    return dict(updates, status=status)
