"""Real SDK subprocess integration tests; no model API or credentials needed."""
import asyncio
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from p2_function_calling.practice.mcp_client import connect, CourseClient
from p2_function_calling.practice.solution import run
from p2_function_calling.practice.solution import create_study_task, update_study_task, get_study_task
from p2_function_calling.practice.operations import OperationJournal
from practice_common.model_adapter import DeepSeekAdapter
from practice_common.runtime import ROOT, ScriptedModel, load_jsonl, JsonStore


class MCPTests(unittest.TestCase):
    def setUp(self):
        root = ROOT / 'tmp/mcp-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_protocol_and_persistence(self):
        async def exercise():
            store = self.directory / 'tasks.json'
            async with connect(store) as client:
                names = {s['function']['name'] for s in client.schemas}
                self.assertEqual(names, {'search_notes', 'read_note', 'create_study_task', 'get_study_task', 'update_study_task'})
                self.assertTrue(client.initialization.protocolVersion)
                resources = await client.session.list_resources()
                self.assertEqual(str(resources.resources[0].uri), 'course://catalog')
                resource = await client.session.read_resource('course://catalog')
                self.assertIn('p2-note', json.loads(resource.contents[0].text))
                prompts = await client.session.list_prompts()
                self.assertEqual(prompts.prompts[0].name, 'compare_papers')
                prompt = await client.session.get_prompt('compare_papers', {'topic_a': 'ReAct', 'topic_b': 'Toolformer'})
                self.assertIn('ReAct', prompt.messages[0].content.text)
                search = await client.call_tool('search_notes', {'query': 'Toolformer'})
                first = search['evidence'][0]
                read = await client.call_tool('read_note', dict(doc_id=first['doc_id'], paragraph_id=first['paragraph_id']))
                self.assertEqual(read['evidence'][0]['text'], first['text'])
                with self.assertRaises(ValueError):
                    await client.call_tool('create_study_task', {})
                arguments = dict(title='Study Toolformer', due_date='2026-10-16', source_ids=['p2-note'], operation_id='test-1')
                created = await client.call_tool('create_study_task', arguments)
                retry = await client.call_tool('create_study_task', arguments)
                self.assertTrue(retry['idempotent'])
                self.assertEqual(retry['task_id'], created['task_id'])
                with self.assertRaises(ValueError):
                    await client.call_tool('create_study_task', dict(arguments, title='Different title'))
                with self.assertRaises(ValueError):
                    await client.call_tool('read_note', dict(doc_id='missing', paragraph_id='1'))
                with self.assertRaises(ValueError):
                    await client.call_tool('unknown_tool', {})
                updated = await client.call_tool('update_study_task', dict(task_id=created['task_id'], operation_id='update-1', title='Updated title'))
                self.assertEqual(updated['title'], 'Updated title')
                # Retrying original create after update checks saved operation arguments/result.
                retried_create = await client.call_tool('create_study_task', arguments)
                self.assertEqual(retried_create['title'], 'Study Toolformer')
            # A fresh server must read the same persisted record.
            async with connect(store) as client:
                task = await client.call_tool('get_study_task', {'task_id': created['task_id']})
                self.assertEqual(task['title'], 'Updated title')
            self.assertEqual(len(json.loads(store.read_text(encoding='utf-8'))['tasks']), 1)
        asyncio.run(exercise())

    def test_agent_routes_all_tools_through_mcp(self):
        calls = [
            dict(type='tool_calls', calls=[
                dict(call_id='s', name='search_notes', arguments={'query': 'Toolformer'}),
                dict(call_id='r', name='read_note', arguments={'doc_id': 'p2-note', 'paragraph_id': '9'})]),
            dict(type='tool_call', call_id='w', name='create_study_task', arguments=dict(title='Study', due_date='2026-10-16', source_ids=['p2-note'])),
            dict(type='tool_call', call_id='g', name='get_study_task', arguments={'task_id': 'task-0001'}),
            dict(type='final', answer='Done'),
        ]
        model = ScriptedModel(calls)
        result = run({'question': 'Create and read back'}, model=model,
                     corpus=load_jsonl(ROOT/'data/corpus.jsonl'), config={'timeout_seconds': 10},
                     artifact_dir=self.directory)
        self.assertEqual(result['transport'], 'mcp')
        self.assertEqual(result['metrics']['tool_calls'], 4)
        self.assertEqual(result['status'], 'completed')
        schemas = model.history[0]['tools']
        self.assertIsInstance(schemas[0], dict)
        for schema in schemas:
            self.assertNotIn('operation_id', schema['function']['parameters']['properties'])
            self.assertNotIn('request_id', schema['function']['parameters']['properties'])
        prepared = DeepSeekAdapter._prepare_messages(model.history[1]['messages'])
        assistant = next(m for m in prepared if m['role'] == 'assistant')
        self.assertEqual([call['id'] for call in assistant['tool_calls']], ['s', 'r'])
        self.assertEqual(len(json.loads((self.directory/'study_tasks.json').read_text())['tasks']), 1)

    def test_lost_response_retries_frozen_operation(self):
        store = JsonStore(self.directory/'tasks.json')
        journal = OperationJournal(self.directory/'journal.json', 'run-1')
        received = []
        def write(**arguments):
            received.append(dict(arguments))
            result = create_study_task(store=store, **arguments)
            if len(received) == 1:
                raise RuntimeError('response lost after successful write')
            return result
        arguments = dict(title='Study', due_date='2026-10-16', source_ids=['p2-note'])
        result = journal.execute('create_study_task', arguments, 'call-1', write)
        self.assertEqual(received[0], received[1])
        self.assertTrue(result['idempotent'])
        self.assertEqual(len(store.read()['tasks']), 1)
        self.assertEqual(journal.store.read()['operations']['run-1:call-1']['status'], 'succeeded')

    def test_restart_resume_and_legacy_data_preserved(self):
        store = JsonStore(self.directory/'tasks.json')
        store.write(dict(tasks={'task-0003': dict(task_id='task-0003', title='Old', request_id='old')},
                         request_ids={'old': 'task-0003'}))
        journal_path = self.directory/'journal.json'
        journal = OperationJournal(journal_path, 'run-1', retries=0)
        def lost(**arguments):
            create_study_task(store=store, **arguments)
            raise RuntimeError('response lost')
        arguments = dict(title='New', due_date='2026-10-16', source_ids=['p2-note'])
        with self.assertRaises(RuntimeError):
            journal.execute('create_study_task', arguments, 'call-1', lost)
        record = journal.store.read()['operations']['run-1:call-1']
        self.assertEqual(record['status'], 'outcome_unknown')
        restarted = OperationJournal(journal_path, 'run-2')
        result = restarted.resume(record['operation_id'], {'create_study_task': lambda **kw: create_study_task(store=store, **kw)})
        self.assertEqual(result['task_id'], 'task-0004')
        self.assertTrue(result['idempotent'])
        self.assertEqual(len(store.read()['tasks']), 2)
        self.assertEqual(store.read()['request_ids'], {'old': 'task-0003'})

    def test_new_runs_are_new_operations(self):
        for title in ('First title', 'Another title'):
            model = ScriptedModel([
                dict(type='tool_call', call_id='same-model-call-id', name='create_study_task',
                     arguments=dict(title=title, due_date='2026-10-16', source_ids=['p2-note'])),
                dict(type='final', answer='Done')])
            result = run(dict(transport='local', request_id='old-fixed-sample'), model=model,
                         corpus=load_jsonl(ROOT/'data/corpus.jsonl'), artifact_dir=self.directory)
            self.assertEqual(result['write_status'], 'succeeded')
            self.assertNotIn('old-fixed-sample', model.history[0]['messages'][1]['content'])
        self.assertEqual(len(JsonStore(self.directory/'study_tasks.json').read()['tasks']), 2)

    def test_failed_write_is_not_completed(self):
        model = ScriptedModel([
            dict(type='tool_call', call_id='bad', name='create_study_task', arguments={}),
            dict(type='final', answer='Done')])
        result = run(dict(transport='local'), model=model, corpus=[], artifact_dir=self.directory)
        self.assertEqual(result['status'], 'failed')

    def test_update_retry_keeps_one_operation(self):
        store = JsonStore(self.directory/'tasks.json')
        task = create_study_task('Original', '2026-10-16', ['p2-note'], 'create-1', store)
        first = update_study_task(task['task_id'], 'update-1', store, title='Changed')
        retry = update_study_task(task['task_id'], 'update-1', store, title='Changed')
        self.assertTrue(retry['idempotent'])
        self.assertEqual(first['title'], retry['title'])
        self.assertEqual(len(store.read()['tasks']), 1)

    def test_real_mcp_lost_response_and_resume_entry(self):
        original = CourseClient.call_tool
        identifiers = []
        async def lose_response(client, name, arguments):
            result = await original(client, name, arguments)
            if name == 'create_study_task':
                identifiers.append(arguments['operation_id'])
                raise RuntimeError('response lost after server write')
            return result
        model = ScriptedModel([
            dict(type='tool_call', call_id='write', name='create_study_task',
                 arguments=dict(title='Frozen', due_date='2026-10-16', source_ids=['p2-note'])),
            dict(type='final', answer='Should not run')])
        context = dict(model=model, corpus=load_jsonl(ROOT/'data/corpus.jsonl'), artifact_dir=self.directory,
                       config={'timeout_seconds': 10})
        with patch.object(CourseClient, 'call_tool', lose_response):
            result = run({}, **context)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(model.calls, 1)  # Stop; do not let model create another operation.
        self.assertEqual(len(identifiers), 2)
        self.assertEqual(identifiers[0], identifiers[1])
        resumed = run({'resume_operation_id': identifiers[0]}, **context)
        self.assertTrue(resumed['recovered_operation']['idempotent'])
        self.assertEqual(model.calls, 1)  # Resume does not call the model.
        self.assertEqual(len(JsonStore(self.directory/'study_tasks.json').read()['tasks']), 1)


if __name__ == '__main__':
    unittest.main()
