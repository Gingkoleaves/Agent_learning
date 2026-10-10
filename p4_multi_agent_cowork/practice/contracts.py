from typing import List, TypedDict


class Message(TypedDict):
    sender: str
    receiver: str
    task_id: str
    kind: str
    body: str
    evidence_ids: List[str]


class AgendaItem(TypedDict):
    owner: str
    topic: str
    minutes: int
    evidence_ids: List[str]


class Plan(TypedDict):
    date: str
    start: str
    end: str
    agenda: List[AgendaItem]
