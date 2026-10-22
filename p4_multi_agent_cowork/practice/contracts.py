from typing import TypedDict


class Message(TypedDict):
    sender: str
    receiver: str
    task_id: str
    kind: str
    body: str
    evidence_ids: list[str]


class AgendaItem(TypedDict):
    owner: str
    topic: str
    minutes: int
    evidence_ids: list[str]


class Plan(TypedDict):
    date: str
    start: str
    end: str
    agenda: list[AgendaItem]
    preparation: str


class Reflection(TypedDict):
    """这是推断，不是新的事实；source_ids 指向角色收到的消息。"""
    kind: str
    inference: str
    source_ids: list[str]
    next_action: str
