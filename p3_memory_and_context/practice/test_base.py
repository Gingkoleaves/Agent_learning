import tempfile
import unittest
from pathlib import Path

from practice_common.runtime import JsonStore, ScriptedModel
from .embeddings import HashEmbedding
from .solution import build_index, retrieve, update_profile, build_context, run


CORPUS = [dict(doc_id="memory", paragraph_id="1", source="memory.md",
               text="MemGPT working context 保存长期重要事实，FIFO 保存最近消息与工具返回。"),
          dict(doc_id="rag", paragraph_id="1", source="rag.md",
               text="RAG 检索器检索外部文档，生成器依据问题和证据生成回答，并提供来源引用。")]


class BaseTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parent / "artifacts" / "tests"
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.path = Path(self.tmp.name)
        self.embedding = HashEmbedding()

    def tearDown(self):
        assert self.path.resolve().is_relative_to((Path(__file__).parent / "artifacts" / "tests").resolve())
        self.tmp.cleanup()

    def test_index_cache_and_source_invalidation(self):
        first = build_index(CORPUS, artifact_dir=self.path, embedder=self.embedding)
        self.assertEqual(retrieve("FIFO working context", first)[0]["doc_id"], "memory")
        cached = build_index(CORPUS, artifact_dir=self.path, embedder=self.embedding)
        self.assertEqual(first["digest"], cached["digest"])
        changed = build_index([dict(CORPUS[0], text=CORPUS[0]["text"] + "补充信息")], artifact_dir=self.path, embedder=self.embedding)
        self.assertNotEqual(first["digest"], changed["digest"])

    def test_profile_update_restart_isolation_and_validation(self):
        store = JsonStore(self.path / "profiles.json")
        update_profile("a", {"minutes_per_day": {"value": 45, "source": "msg-1"}}, store)
        update_profile("a", {"minutes_per_day": {"value": 20, "source": "msg-2"}}, store)
        recovered = update_profile("a", {}, JsonStore(store.path))
        self.assertEqual(recovered["facts"]["minutes_per_day"]["value"], 20)
        self.assertEqual(recovered["history"][0]["source"], "msg-1")
        self.assertEqual(update_profile("b", {}, store)["facts"], {})
        before = store.read()
        with self.assertRaises(ValueError):
            update_profile("a", {"minutes_per_day": -1}, store)
        self.assertEqual(before, store.read())

    def test_context_all_strategies_budget_and_latest_question(self):
        messages = [{"role": "user", "content": "旧消息" * 100}] * 20 + [{"role": "user", "content": "解释 FIFO"}]
        evidence = [dict(CORPUS[0], chunk_id="memory:1:0")]
        for strategy in ("truncate", "summary", "summary_retrieval"):
            built = build_context(messages, {}, evidence, strategy, 1600)
            self.assertLessEqual(built["input_tokens_estimate"], 1600)
            self.assertEqual(built["messages"][-1], messages[-1])
            self.assertIn("memory:1:0", built["included_chunk_ids"])
        with self.assertRaisesRegex(ValueError, "context_overflow"):
            build_context(messages, {}, evidence, "truncate", 10)

    def test_invalid_citation_is_not_success(self):
        result = run({"user_id": "a", "question": "解释 FIFO"},
                     corpus=CORPUS, embedder=self.embedding, artifact_dir=self.path,
                     model=ScriptedModel([{"type": "final", "answer": "答案 [invented:1]"}]),
                     config={"context_token_budget": 5000})
        self.assertEqual(result["status"], "invalid_citations")
        self.assertEqual(result["invalid_citations"], ["invented:1"])

    def test_model_gets_actual_evidence_and_current_profile(self):
        model = ScriptedModel([{"type": "final", "answer": "事实保存在工作上下文 [memory:1:0]"}])
        result = run({"user_id": "a", "question": "解释 FIFO working context", "facts": {"minutes_per_day": 20}},
                     corpus=CORPUS, embedder=self.embedding, artifact_dir=self.path, model=model,
                     config={"context_token_budget": 5000})
        self.assertEqual(result["status"], "generated_ungraded")
        self.assertIn("20", model.history[0]["messages"][0]["content"])
        self.assertIn(CORPUS[0]["text"], model.history[0]["messages"][0]["content"])
        self.assertEqual(result["citations"][0]["source"], "memory.md")

    def test_zero_call_budget_stops_before_generation(self):
        model = ScriptedModel([])
        result = run({"user_id": "a", "question": "解释 FIFO"}, corpus=CORPUS,
                     embedder=self.embedding, artifact_dir=self.path, model=model,
                     config={"max_model_calls": 0, "context_token_budget": 5000})
        self.assertEqual(result["status"], "error")
        self.assertEqual(model.calls, 0)


if __name__ == "__main__":
    unittest.main()
