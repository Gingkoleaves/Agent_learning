"""Regression tests for grading errors, isolation, retries and trace ancestry."""
import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from practice_common.model_adapter import DeepSeekAdapter
from practice_common.runtime import ROOT, JsonStore, load_json, load_jsonl
from .agent import Backend
from .observability import Observability, Recorder, ObservedModel
from .offline import OfflineModel
from .solution import HERE, _load_suite, _trial, evaluate_case, reset_environment, snapshot, summarize, validate_case


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cases = _load_suite(HERE / 'data/cases.jsonl', 30, True)
        self.corpus = load_jsonl(ROOT / 'data/corpus.jsonl')
        self.config = load_json(HERE / 'config.json')

    def tearDown(self):
        self.temp.cleanup()

    def case(self, name):
        return deepcopy(next(c for c in self.cases if c['id'] == name))

    def trial(self, case, variant='fixed', model=None, config=None):
        obs = Observability(self.root)
        try:
            return asyncio.run(_trial(case, 1, variant, 'test', self.root, obs,
                dict(corpus=self.corpus, config=config or self.config, model=model)))
        finally:
            obs.close()

    def test_annotations_and_balanced_development(self):
        self.assertEqual(len(self.cases), 30)
        for c in self.cases:
            validate_case(c)
            self.assertTrue(c['rubric'])
        # Holdout is intentionally not executed or used for tuning in tests.

    def test_unannotated_and_missing_final_state_rejected(self):
        for change in ({'fixture_only': True}, {'annotation_status': 'TODO'}, {'expected_final_state': None}):
            c = dict(self.cases[0], **change)
            with self.assertRaises(ValueError):
                evaluate_case(c, {}, {})

    def test_environment_isolation_and_no_stale_checkpoints(self):
        initial = self.case('memory-01')['initial_state']
        original = deepcopy(initial)
        one = reset_environment(initial, artifact_dir=self.root / 'one')
        two = reset_environment(initial, artifact_dir=self.root / 'two')
        JsonStore(one['artifact_dir'] / 'study_tasks.json').write({'tasks': {'changed': {}}})
        self.assertEqual(snapshot(two['artifact_dir'])['task_count'], 0)
        self.assertEqual(initial, original)
        self.assertNotEqual(one['session_id'], two['session_id'])
        with self.assertRaises(FileExistsError):
            reset_environment(initial, artifact_dir=self.root / 'one')

    def test_fake_success_is_detected_by_database(self):
        row = self.trial(self.case('fault-03'), 'baseline')
        self.assertTrue(row['actual']['claimed_saved'])
        self.assertFalse(row['success'])
        self.assertFalse(row['checks']['final_state'])
        self.assertFalse(row['details']['rules']['truthful_save'])

    def test_fake_update_success_checks_content_not_only_id(self):
        row = self.trial(self.case('fault-04'), 'baseline')
        self.assertEqual(row['final_state']['task_count'], 1)
        self.assertFalse(row['details']['rules']['truthful_save'])

    def test_readback_fix_retries_real_write(self):
        row = self.trial(self.case('fault-03'))
        self.assertTrue(row['success'], row)
        self.assertEqual(row['final_state']['operation_count'], 1)
        events = load_jsonl(self.root / row['trace_path'])
        self.assertTrue(any(e['event'] == 'retry' and e['stage'] == 'save' for e in events))

    def test_lost_ack_retry_uses_same_operation(self):
        row = self.trial(self.case('fault-05'))
        self.assertTrue(row['success'], row)
        self.assertEqual(row['final_state']['task_count'], 1)
        events = load_jsonl(self.root / row['trace_path'])
        ids = [e['arguments']['operation_id'] for e in events if e['event'] == 'tool_start' and e['name'] == 'create_study_task']
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 1)

    def test_transient_failure_recovery_is_bounded(self):
        case = self.case('fault-01')
        case['faults'] = {'search_transient': 3}
        row = self.trial(case)
        self.assertFalse(row['success'])
        events = load_jsonl(self.root / row['trace_path'])
        self.assertEqual(sum(e['event'] == 'tool_start' and e['name'] == 'search_notes' for e in events), 2)

    def test_confirmation_not_inferred(self):
        for name in ('plan-02', 'plan-03'):
            row = self.trial(self.case(name))
            self.assertTrue(row['success'], row)
            self.assertEqual(row['final_state']['task_count'], 0)

    def test_replay_completed_checkpoint_does_not_write_again(self):
        row = self.trial(self.case('plan-04'))
        self.assertTrue(row['success'], row)
        events = load_jsonl(self.root / row['trace_path'])
        self.assertEqual(sum(e['event'] == 'tool_start' and e['name'] == 'create_study_task' for e in events), 1)

    def test_latest_profile_and_user_isolation(self):
        row = self.trial(self.case('memory-04'))
        self.assertTrue(row['success'], row)
        self.assertEqual(row['actual']['profile']['minutes_per_day'], 25)
        self.assertEqual(row['final_state']['profiles']['other']['minutes_per_day'], 90)

    def test_existing_but_unsupported_citation_fails(self):
        case = self.case('knowledge-05')
        actual = dict(status='answered', answer='自监督', citations=[{'doc_id': 'p2-note', 'paragraph_id': '1'}],
            claims=[{'doc_id': 'p2-note', 'paragraph_id': '1', 'text': '自监督', 'quote': '自监督'}],
            _observed_evidence_ids=['p2-note:1'], _events=[{'event': 'tool_start', 'name': 'search_notes'}])
        score = evaluate_case(case, actual, case['expected_final_state'], corpus=self.corpus)
        self.assertTrue(score['checks']['citation_exists'])
        self.assertFalse(score['checks']['quotes'])
        self.assertFalse(score['success'])

    def test_correct_source_with_negated_answer_does_not_auto_pass(self):
        case = self.case('knowledge-05')
        source = next(e for e in self.corpus if e['doc_id'] == 'p2-note' and e['paragraph_id'] == '10')
        actual = dict(status='answered', answer='Toolformer不是自监督训练。',
            citations=[{'doc_id': 'p2-note', 'paragraph_id': '10'}],
            claims=[dict(source, text='并不是自监督，不依据预测概率，也不是只保留。', quote=source['text'])],
            _observed_evidence_ids=['p2-note:10'], _events=[{'event': 'tool_start', 'name': 'search_notes'}])
        score = evaluate_case(case, actual, case['expected_final_state'], corpus=self.corpus)
        self.assertFalse(score['success'])
        self.assertEqual(score['semantic_review'], 'human_review_required')

    def test_missing_evidence_does_not_accept_empty_or_fabricated_answer(self):
        case = self.case('fault-06')
        for answer in ('', '已经证明，答案为42。'):
            score = evaluate_case(case, dict(status='no_evidence', answer=answer, citations=[],
                _events=[{'event': 'tool_start', 'name': 'search_notes'}]), case['expected_final_state'])
            self.assertFalse(score['success'])

    def test_malformed_output_fails_without_crashing(self):
        for actual in (None, [], {'answer': 3, 'citations': 'x'}, {'answer': '', 'citations': [None]}):
            score = evaluate_case(self.cases[0], actual, {})
            self.assertFalse(score['success'])

    def test_percentiles_three_trials_and_empty_suite(self):
        rows = [dict(case_id='a', category='knowledge', trial=i + 1, success=i != 1,
            model_calls=i + 1, tool_calls=1, duration_seconds=t, checks={}, usage={}) for i, t in enumerate([1, 2, 9])]
        summary = summarize(rows)
        self.assertAlmostEqual(summary['single_success_rate'], 2 / 3)
        self.assertEqual(summary['all_three_success_rate'], 0)
        self.assertEqual(summary['p50_seconds'], 2)
        self.assertAlmostEqual(summary['p95_seconds'], 8.3)
        self.assertIsNone(summarize(rows[:1])['all_three_success_rate'])
        self.assertIsNone(summarize([])['single_success_rate'])
        with self.assertRaises(ValueError):
            summarize(rows + [rows[0]])

    def test_deadline_cancels_model_before_write(self):
        class SlowModel:
            async def arespond(self, *args):
                await asyncio.sleep(60)
        row = self.trial(self.case('plan-01'), model=SlowModel(), config=dict(self.config, timeout_seconds=.1))
        self.assertEqual(row['actual']['status'], 'timeout')
        self.assertEqual(row['final_state']['task_count'], 0)
        self.assertLess(row['duration_seconds'], 2)

    def test_model_and_tool_budgets(self):
        obs = Observability(self.root)
        recorder = Recorder(self.root / 'trace.jsonl', obs, max_tools=1)
        recorder.tool('one', lambda: 1)
        with self.assertRaisesRegex(RuntimeError, 'tool_call_budget'):
            recorder.tool('two', lambda: 2)
        model = ObservedModel(OfflineModel(), recorder, max_calls=0)
        with self.assertRaisesRegex(RuntimeError, 'model_call_budget'):
            asyncio.run(model.arespond([]))
        obs.close()

    def test_span_parentage_and_exception_status(self):
        obs = Observability(self.root)
        recorder = Recorder(self.root / 'trace.jsonl', obs)
        with obs.span('task'):
            recorder.tool('read', lambda: {'ok': True})
            with self.assertRaises(ValueError):
                recorder.tool('broken', lambda: (_ for _ in ()).throw(ValueError('injected')))
        obs.close()
        spans = load_jsonl(self.root / 'spans.jsonl')
        parent = next(s for s in spans if s['name'] == 'task')
        for child in [s for s in spans if s['name'].startswith('tool.')]:
            self.assertEqual(child['parent_id'], parent['context']['span_id'])
            self.assertEqual(child['context']['trace_id'], parent['context']['trace_id'])
        self.assertEqual(next(s for s in spans if s['name'] == 'tool.broken')['status']['status_code'], 'ERROR')

    def test_model_adapter_roundtrip_and_usage_without_network(self):
        adapter = DeepSeekAdapter('test-only')
        response = adapter._parse_response({'usage': {'total_tokens': 7}, 'choices': [{'message': {
            'tool_calls': [{'id': 'real-call-id', 'function': {'name': 'search_notes', 'arguments': '{"query":"MCP"}'}}]}}]})
        self.assertEqual(response['call_id'], 'real-call-id')
        messages = adapter._prepare_messages([{'role': 'assistant', 'content': response},
            {'role': 'tool', 'tool_call_id': response['call_id'], 'content': '{"evidence":[]}'}])
        self.assertEqual(messages[0]['tool_calls'][0]['id'], messages[1]['tool_call_id'])
        self.assertEqual(adapter.total_usage['total_tokens'], 7)

    def test_annotation_labels_never_cross_agent_boundary(self):
        seen = []
        async def spy(request, **context):
            seen.append(deepcopy(request))
            return {'status': 'error', 'answer': '', 'citations': []}
        with patch('p6_evaluation.practice.agent.execute', spy):
            self.trial(self.cases[0])
        self.assertEqual(set(seen[0]), {'input', 'user_script', 'faults'})

    def test_langsmith_explicitly_reports_missing_configuration(self):
        with patch.dict('os.environ', {}, clear=True):
            obs = Observability(self.root, langsmith=True)
            self.assertEqual(obs.langsmith['status'], 'not_configured')
            obs.close()

    def test_review_pending_is_not_a_passing_semantic_score(self):
        from .review import apply_reviews
        from practice_common.runtime import save_json
        rows = [dict(case_id='test', trial=1, variant='fixed', trace_path='trace.jsonl',
                     actual={'answer': 'answer'}, checks={'final_state': True, 'citation_support': True})]
        (self.root / 'results.jsonl').write_text(json.dumps(rows[0]) + '\n')
        reviews = [dict(case_id='test', trial=1, variant='fixed', trace_path='trace.jsonl',
                        answer='answer', reviewer=None, semantic_correct=None)]
        save_json(self.root / 'human_review.json', reviews)
        result = apply_reviews(self.root)
        self.assertEqual(result['pending_runs'], 1)
        self.assertIsNone(result['summary'])
        reviews[0]['semantic_correct'] = True
        save_json(self.root / 'human_review.json', reviews)
        with self.assertRaises(ValueError):
            apply_reviews(self.root)

    def test_langsmith_sample_has_one_root_and_verifies_upload(self):
        from unittest.mock import MagicMock
        client, root, child = MagicMock(), MagicMock(), MagicMock()
        root.id = 'test-run'
        root.get_url.return_value = 'https://example.invalid/test-run'
        root.create_child.return_value = child
        with patch.dict('os.environ', {'LANGSMITH_API_KEY': 'test-only'}), \
             patch('langsmith.Client', return_value=client), patch('langsmith.RunTree', return_value=root):
            obs = Observability(self.root, langsmith=True)
            with obs.span('task', case_id='sample'):
                with obs.span('model.call'):
                    obs.annotate(inputs={'messages': []}, outputs={'answer': 'sample'})
            with obs.span('task', case_id='another'):
                pass
            self.assertEqual(obs.langsmith['status'], 'verified')
            root.post.assert_called_once()
            child.post.assert_called_once()
            child.add_outputs.assert_called_once()
            client.read_run.assert_called_once_with('test-run')
            obs.close()


if __name__ == '__main__':
    unittest.main()
