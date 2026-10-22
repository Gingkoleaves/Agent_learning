"""只用标准库 unittest。验证最容易出现的真实逻辑错误。"""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from practice_common.runtime import Trace, load_json, load_jsonl
from .experiment import case_input, launch
from .models import make_model, resolve_provider
from practice_common.model_adapter import DeepSeekAdapter
from .offline import OfflineModel
from .solution import HERE, build_team, reflect, route_message, run, validate_plan


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.corpus = load_jsonl(HERE / "data/corpus.jsonl")

    def execute(self, case=None, **kwargs):
        kwargs.setdefault("model", OfflineModel())
        return run(case_input(case or {"id": "test"}, "multi_reflection"),
                   artifact_dir=self.folder, corpus=self.corpus, **kwargs)

    def test_provider_selection(self):
        config = {"provider": "deepseek", "max_model_calls": 18, "timeout_seconds": 30}
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_provider(config=config), "deepseek")
            with patch("p4_multi_agent_cowork.practice.models.load_deepseek_key", return_value="test"):
                self.assertIsInstance(make_model(config=config), DeepSeekAdapter)
        with patch.dict(os.environ, {"MODEL_PROVIDER": "deepseek"}):
            self.assertEqual(resolve_provider(config={"provider": "offline"}), "deepseek")
            self.assertEqual(resolve_provider("offline", config), "offline")
            from practice_common.cli import main
            with patch("p4_multi_agent_cowork.practice.experiment.launch", return_value=0) as start:
                main(["4", "run"])
                start.assert_called_once_with(None, None, False)
            with patch("p4_multi_agent_cowork.practice.experiment.evaluate",
                       return_value={"passed": 24, "total": 24}) as evaluate:
                self.assertEqual(launch(evaluate_all=True), 0)
                evaluate.assert_called_once_with("deepseek")

    def test_run_uses_factory_without_replacing_explicit_model(self):
        model = OfflineModel()
        with patch("p4_multi_agent_cowork.practice.solution.make_model", return_value=model) as factory:
            result = run(case_input({"id": "factory"}, "multi"), artifact_dir=self.folder)
            factory.assert_called_once()
            self.assertEqual(result["status"], "completed")
            self.assertGreater(model.calls, 0)
        with patch("p4_multi_agent_cowork.practice.solution.make_model") as factory:
            self.assertEqual(self.execute()["status"], "completed")
            factory.assert_not_called()

    def test_communication_changes_plan_and_reflection_is_used(self):
        result = self.execute()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["before_communication"]["agenda"]), 1)
        self.assertEqual(len(result["after_communication"]["agenda"]), 3)
        self.assertEqual(result["next_plan"]["preparation"],
                         result["agents"]["host"]["reflections"][0]["next_action"])
        for state in result["agents"].values():
            ids = {o["id"] for o in state["observations"]}
            self.assertTrue(set(state["reflections"][0]["source_ids"]) <= ids)

    def test_validate_constraints(self):
        result = self.execute()
        profiles = result["effective_profiles"]
        for change in ("minutes", "owner", "evidence_ids"):
            plan = deepcopy(result["plan"])
            plan["agenda"][0][change] = {"minutes": -3, "owner": "ghost",
                                        "evidence_ids": ["fake:9"]}[change]
            self.assertTrue(validate_plan(plan, profiles, self.corpus))
        self.assertTrue(validate_plan({}, profiles, self.corpus))
        plan = deepcopy(result["plan"])
        plan["date"] = "2026-10-24"
        self.assertTrue(validate_plan(plan, profiles, self.corpus))

    def test_budget_and_round_limits(self):
        config = {"max_model_calls": 1, "max_rounds": 6, "timeout_seconds": 30}
        self.assertEqual(self.execute(config=config)["status"], "budget_exhausted")
        config["max_model_calls"] = 18
        config["max_rounds"] = 1
        result = self.execute({"id": "fault", "fault": "forged_reference"}, config=config)
        self.assertEqual(result["status"], "invalid_plan")
        self.assertEqual(result["rounds"], 1)

    def test_fault_repair_and_missing_role(self):
        for fault in ("time_conflict", "forged_reference"):
            result = self.execute({"id": fault, "fault": fault})
            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["repairs"])
        result = self.execute({"id": "absent", "fault": "absent"})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["missing"], ["critic"])
        self.assertNotIn("critic", [a["owner"] for a in result["plan"]["agenda"]])

    def test_json_and_next_plan_repair(self):
        class BrokenOnce(OfflineModel):
            broken_json = False
            broken_next = False

            def respond(self, messages, tools=None):
                reply = super().respond(messages, tools)
                stage = json.loads(messages[-1]["content"])["stage"]
                if not self.broken_json:
                    self.broken_json = True
                    return {"answer": "这不是 JSON"}
                if stage == "next_plan" and not self.broken_next:
                    self.broken_next = True
                    plan = json.loads(reply["answer"])
                    plan["agenda"][0]["minutes"] = 999
                    return {"answer": json.dumps(plan)}
                return reply

        result = self.execute(model=BrokenOnce())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["next_repairs"]), 1)
        self.assertTrue(any("format_error" in m["body"] for m in result["messages"]))

    def test_model_answer_must_be_an_object(self):
        for answer in ("null", "[]"):
            with self.subTest(answer=answer):
                model = OfflineModel()
                model.respond = lambda *args: {"answer": answer}
                result = self.execute(model=model)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["reason"], "模型回答必须是 JSON 对象")

    def test_routing_isolation_and_invalid_reflection(self):
        async def check():
            profiles = load_json(HERE / "data/profiles.json")
            model = OfflineModel()
            team = await build_team(profiles, model=model, corpus=self.corpus,
                                    trace=Trace(self.folder / "trace.jsonl"),
                                    task_id="test", timeout=1)
            msg = dict(sender="host", receiver="researcher", task_id="test",
                       kind="feedback", body='{"notice":"仅资料员可见"}', evidence_ids=[])
            try:
                await route_message(msg, team)
                self.assertEqual(len(team["states"]["researcher"]["observations"]), 1)
                self.assertEqual(team["states"]["critic"]["observations"], [])
                with self.assertRaises(ValueError):
                    await route_message(dict(msg, task_id="other"), team)
                with self.assertRaises(ValueError):
                    await route_message(dict(msg, receiver="unknown"), team)
                model.respond = lambda *a: {"answer": json.dumps({
                    "inference": "伪造经验", "source_ids": ["unknown"], "next_action": "改变计划"})}
                with self.assertRaises(ValueError):
                    await reflect(team["states"]["researcher"]["observations"],
                                  team=team, who="researcher")
            finally:
                await team["runtime"].stop()
                await team["runtime"].close()
        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
