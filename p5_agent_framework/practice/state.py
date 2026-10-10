from typing import Any, Dict, List, Optional, TypedDict


class StudyState(TypedDict):
    session_id: str
    question: str
    evidence: List[Dict[str, Any]]
    candidate_plan: Optional[Dict[str, Any]]
    validation_errors: List[str]
    user_decision: Optional[bool]
    request_id: str
    saved_task_id: Optional[str]
    revision_count: int


# TODO(P5-STATE): decide reducers, initialization and allowed state transitions.
# user_decision=None is pending; it must never be treated as approval.
