"""规则替身，只验证协议和恢复，不能证明真实 LLM 的协作能力。

它读取与真实模型相同的 prompt，用时间/主题/证据计算计划，不返回固定答案。
"""
import json

from .planning import common_window


class OfflineModel:
    def __init__(self):
        self.calls = 0
        self.max_calls = 18
        self.total_usage = {}

    def respond(self, messages, tools=None):
        if self.calls >= self.max_calls:
            raise RuntimeError("model_call_budget_exhausted")
        self.calls += 1
        data = json.loads(messages[-1]["content"])
        if data["stage"] == "review":
            answer = {"issues": data["task"].get("validation_errors", [])}
        elif data["stage"] == "reflect":
            observations = data["observations"]
            relevant = [o for o in observations if o["kind"] == "update"
                        or "validation_errors" in o["body"]]
            source = (relevant or observations)[-1]
            answer = {"inference": "新收到的约束会改变议程，不能只依据自己的档案。",
                      "source_ids": [source["id"]],
                      "next_action": "会前再次确认每人的可用时间与引用来源。"}
        else:
            answer = self.plan(data)
        return {"type": "final", "answer": json.dumps(answer, ensure_ascii=False)}

    @staticmethod
    def plan(data):
        own = data["profile"]
        profiles = {own["id"]: own}
        evidence = list(data["evidence"])
        for observation in data["observations"]:
            body = json.loads(observation["body"])
            if observation["kind"] in ("profile", "update"):
                profile = body["profile"]
                profiles[profile["id"]] = profile
                evidence.extend(body.get("evidence", []))
        window = common_window(list(profiles.values()))
        if window is None:
            raise ValueError("无共同时间")
        day, start, end = window
        tasks = [(p["id"], t) for p in profiles.values() for t in p["known_topics"]]
        duration = (end - start) // len(tasks)
        agenda = []
        for owner, topic in tasks:
            refs = [e["id"] for e in evidence if topic.lower() in e["text"].lower()]
            agenda.append({"owner": owner, "topic": topic, "minutes": duration,
                           "evidence_ids": refs[:1]})
        reflections = data["reflections"]
        return {"date": day, "start": f"{start // 60:02}:{start % 60:02}",
                "end": f"{end // 60:02}:{end % 60:02}", "agenda": agenda,
                "preparation": reflections[-1]["next_action"] if reflections else "各自阅读负责的资料。"}
