"""Transparent extractive fixture, never given expected facts or final states."""
import json

from p5_agent_framework.practice.offline import OfflineModel as PlanModel


class OfflineModel(PlanModel):
    model_name = 'offline-extractive-and-p5-plan-fixture'

    def respond(self, messages, tools=None):
        if not tools:
            return super().respond(messages, tools)
        self.calls += 1
        request = next(json.loads(m['content']) for m in messages if m['role'] == 'user')
        results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
        completed = {r['query'] for r in results if 'query' in r and 'error' not in r}
        pending = [q for q in request['queries'] if q not in completed]
        if pending:
            return dict(type='tool_call', call_id=f'search-{self.calls}', name='search_notes',
                        arguments={'query': pending[0]})
        evidence = {}
        for result in results:
            for e in result.get('evidence', []):
                if len(e['text']) >= 25 and not e['text'].startswith('!['):
                    evidence[(e['doc_id'], e['paragraph_id'])] = e
        claims = [dict(text=e['text'], quote=e['text'], doc_id=e['doc_id'], paragraph_id=e['paragraph_id'])
                  for e in evidence.values()]
        answer = '\n\n'.join(c['text'] for c in claims) if claims else '资料中没有依据，无法回答。'
        return dict(type='final', answer=json.dumps(dict(answer=answer, claims=claims,
                    citations=[{'doc_id': c['doc_id'], 'paragraph_id': c['paragraph_id']} for c in claims]), ensure_ascii=False))
