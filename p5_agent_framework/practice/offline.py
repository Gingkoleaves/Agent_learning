"""Offline demonstration model for running the graph without an API key."""
import json
from datetime import date, timedelta

class OfflineModel:
    model_name = 'offline-rule-fixture'

    def __init__(self):
        self.calls = 0

    def respond(self, messages, tools=None):
        self.calls += 1
        user = next(json.loads(m['content']) for m in messages
                    if m['role'] == 'user' and m['content'].startswith('{'))
        results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
        if not results:
            return dict(type='tool_call', call_id=f'search-{self.calls}', name='search_notes',
                        arguments={'query': user.get('query', 'ReAct')})
        evidence = results[-1]['evidence']
        if not evidence:
            return dict(type='final', answer='{}')
        days = []
        for i in range(3):
            e = evidence[i % len(evidence)]
            days.append(dict(date=(date.fromisoformat(user['start_date']) + timedelta(days=i)).isoformat(),
                minutes=user['profile']['minutes_per_day'],
                activity=f"{'复习' if user['profile'].get('completed') else '学习'} {user.get('query', '')}：阅读 {e['doc_id']} 第 {e['paragraph_id']} 段，写三条要点并练习。",
                citations=[dict(doc_id=e['doc_id'], paragraph_id=e['paragraph_id'])]))
        return dict(type='final', answer=json.dumps(dict(title=user['question'], days=days), ensure_ascii=False))

    async def arespond(self, messages, tools=None):
        return self.respond(messages, tools)
