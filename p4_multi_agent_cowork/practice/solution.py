"""P4：三个角色商量学习计划。先读 collaborate，再读消息投递和角色实现。

AutoGen 负责角色与消息投递；协作顺序直接写在 collaborate 中。
offline.py 是规则替身；真实模型复用公共 DeepSeekAdapter。
"""
import asyncio
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import time

from autogen_core import (
    AgentId, CancellationToken, MessageContext, RoutedAgent,
    SingleThreadedAgentRuntime, message_handler,
)
from practice_common.runtime import Trace, load_json, load_jsonl, save_json
from .contracts import Message, Reflection
from .models import make_model
from .offline import OfflineModel
from .planning import common_window, select_evidence, validate_plan

HERE = Path(__file__).resolve().parent
MODES = ("single", "multi", "multi_reflection")


SYSTEM = """你参加学习讨论的安排。只输出 JSON，不要 Markdown 或隐藏思维。
只能使用自己的档案和收到的消息。profile 消息携带同伴档案与证据；
update 消息覆盖同名角色之前的时间。不能编造证据，不能替缺席角色承诺。
plan/next_plan：输出 {"date":"YYYY-MM-DD","start":"HH:MM","end":"HH:MM",
"agenda":[{"owner":"角色id","topic":"ReAct或Toolformer或MemGPT","minutes":20,
"evidence_ids":["文档id:段落id"]}],"preparation":"简短的会前安排"}。
取在场者时间交集，覆盖在场者所有主题，每人至少负责一项。总时长不能超时。
next_plan 是相同约束下的下一次方案；若有反思，实际用于准备安排。
topic 是固定枚举，只能逐字使用 ReAct、Toolformer、MemGPT。
交叉讨论、总结等说明放入 preparation，不要发明新的 topic。
review：输出 {"issues":["问题及建议"]}，核对收到的草案。
reflect：输出 {"inference":"从经历推断的经验","source_ids":["观察ID"],
"next_action":"下次采取的具体行动"}。推断不是新事实，来源必须是自己的观察。
"""


@dataclass
class Envelope:
    """AutoGen 传递的对象；里面沿用 contracts.py 的消息字段。"""
    message: Message


class StudyAgent(RoutedAgent):
    def __init__(self, state, model, trace):
        super().__init__(state["profile"]["role"])
        self.state, self.model, self.trace = state, model, trace

    @message_handler
    async def receive(self, message: Envelope, ctx: MessageContext) -> dict:
        msg = message.message
        if self.state.get("silent"):
            # 故障测例：一直不回应，外层超时会取消这次处理。
            sleeper = asyncio.create_task(asyncio.sleep(3600))
            ctx.cancellation_token.link_future(sleeper)
            await sleeper
        if msg["kind"] != "request":
            self.state["observations"].append(deepcopy(msg))
            return {"status": "received"}
        request = json.loads(msg["body"])
        # 给当前步骤一个明确边界，避免把 plan 和 next_plan 一起输出。
        instruction = f"当前只做 {request['stage']}，只返回该步骤的单个 JSON 对象。"
        if request["stage"] == "reflect":
            ids = [o["id"] for o in self.state["observations"]]
            instruction += f" observations 就是你的观察；source_ids 至少选择一个实际支持推断的 ID：{ids}。"
        prompt = {"stage": request["stage"], "profile": self.state["profile"],
                  "evidence": self.state["evidence"],
                  "observations": self.state["observations"],
                  "reflections": self.state["reflections"],
                  "task": request.get("task", {})}
        messages = [{"role": "system", "content": SYSTEM + instruction},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}]
        self.trace.emit("model_input", agent=self.id.type, prompt=prompt)
        # 公共接口是同步 HTTP；放在线程内，不堵塞 AutoGen 消息循环。
        reply = await asyncio.to_thread(self.model.respond, messages)
        self.trace.emit("model_output", agent=self.id.type, response=reply)
        content = reply.get("answer", "")
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise TypeError("模型回答必须是 JSON 对象")
        return result


async def build_team(profiles, **context):
    """P4-01：共享模型调用预算，但不共享角色记忆。"""
    runtime, states = SingleThreadedAgentRuntime(), {}
    for profile in profiles:
        state = {"profile": deepcopy(profile),
                 "evidence": select_evidence(profile, context["corpus"]),
                 "observations": [], "reflections": [],
                 "silent": profile["id"] == context.get("absent")}
        states[profile["id"]] = state
        await StudyAgent.register(
            runtime, profile["id"],
            lambda state=state: StudyAgent(state, context["model"], context["trace"]))
    runtime.start()
    return {"runtime": runtime, "states": states, "trace": context["trace"],
            "task_id": context["task_id"], "timeout": context["timeout"],
            "messages": [], "missing": []}


async def route_message(message: Message, team):
    """P4-02：校验消息后，真正经过 AutoGen 投递，而非直接调用另一个模型。"""
    required = ("sender", "receiver", "task_id", "kind", "body", "evidence_ids")
    if any(k not in message for k in required):
        raise ValueError("消息缺少必要字段")
    if any(not isinstance(message[k], str) for k in required[:-1]):
        raise ValueError("消息文本字段必须是字符串")
    if (not isinstance(message["evidence_ids"], list)
            or any(not isinstance(x, str) for x in message["evidence_ids"])):
        raise ValueError("evidence_ids 必须是字符串列表")
    if message["task_id"] != team["task_id"]:
        raise ValueError("消息属于另一个任务")
    if message["receiver"] not in team["states"]:
        raise ValueError("收件角色不存在")
    if message["sender"] not in {*team["states"], "system"}:
        raise ValueError("发件角色不存在")
    if message["kind"] not in {"profile", "update", "proposal", "feedback", "request"}:
        raise ValueError("未知消息类型")
    msg = dict(message, id=f"m{len(team['messages']) + 1}")
    team["messages"].append(msg)
    token = CancellationToken()
    future = asyncio.create_task(team["runtime"].send_message(
        Envelope(msg), AgentId(msg["receiver"], "default"), cancellation_token=token))
    token.link_future(future)
    try:
        result = await asyncio.wait_for(future, team["timeout"])
    except asyncio.TimeoutError:
        token.cancel()
        if msg["receiver"] not in team["missing"]:
            team["missing"].append(msg["receiver"])
        result = {"status": "timeout", "agent": msg["receiver"]}
    team["trace"].emit("message", message=msg, result=result)
    return result


async def send(team, sender, receiver, kind, body, evidence_ids=None):
    return await route_message(
        {"sender": sender, "receiver": receiver, "task_id": team["task_id"],
         "kind": kind, "body": json.dumps(body, ensure_ascii=False),
         "evidence_ids": evidence_ids or []}, team)


async def ask(team, who, stage, task=None):
    # 仅对 JSON 格式错误重试一次；调用仍计入同一个预算。
    for attempt in range(2):
        try:
            result = await send(team, "system", who, "request",
                                {"stage": stage, "task": task or {}})
            break
        except json.JSONDecodeError:
            if attempt == 1:
                raise
            await send(team, "system", who, "feedback",
                       {"format_error": "上次不是合法 JSON。只输出当前步骤的一个对象。"})
    if result.get("status") == "timeout":
        raise TimeoutError(f"{who} 响应超时")
    return result


async def reflect(observations, **context) -> Reflection:
    """P4-03：核对来源，不把推断当成客观事实。"""
    known_ids = {o["id"] for o in observations}
    for attempt in range(2):
        result = await ask(context["team"], context["who"], "reflect")
        if (result.get("inference") and result.get("next_action")
                and result.get("source_ids")
                and set(result["source_ids"]).issubset(known_ids)):
            return dict(result, kind="inference")
        if attempt == 0:
            await send(context["team"], "system", context["who"], "feedback",
                       {"reflection_error": "请引用已有观察，不要留空或编造来源。",
                        "allowed_source_ids": sorted(known_ids)})
    raise ValueError("反思必须引用自己的观察，并给出下一次行动")


async def collaborate(payload, model, corpus, trace, config):
    """P4-05：主流程。按顺序读这一个函数，就能看懂整个实验。"""
    profiles = deepcopy(payload.get("profiles") or load_json(HERE / "data/profiles.json"))
    mode, fault = payload.get("mode", "multi_reflection"), payload.get("fault")
    if mode not in MODES:
        raise ValueError(f"mode 必须是 {MODES}")
    team = await build_team(
        profiles, model=model, corpus=corpus, trace=trace,
        task_id=payload.get("task_id", "discussion-001"),
        timeout=config["timeout_seconds"], absent="critic" if fault == "absent" else None)
    result = {"status": "failed", "plan": None, "next_plan": None,
              "repairs": [], "mode": mode, "rounds": 0}
    try:
        # 1. 先仅凭主持人自己的知识提案，留作“通信前”的证据。
        result["before_communication"] = await ask(team, "host", "plan")

        # 2. 探测缺席。故障测例只等 0.05 秒，正常调用等待 config 的 30 秒。
        for who in ("researcher", "critic"):
            original_timeout = team["timeout"]
            if fault == "absent" and who == "critic":
                team["timeout"] = 0.05
            await send(team, "system", who, "feedback", {"notice": "开始讨论"})
            team["timeout"] = original_timeout
        active = [p for p in profiles if p["id"] not in team["missing"]]

        # 3. 交换档案。single 组仅主持人推理，但拿到相同资料。
        recipients = ["host"] if mode == "single" else [p["id"] for p in active]
        for profile in active:
            who = profile["id"]
            evidence = team["states"][who]["evidence"]
            for receiver in recipients:
                if receiver != who:
                    await send(team, who, receiver, "profile",
                               {"profile": profile, "evidence": evidence},
                               [e["id"] for e in evidence])
        if team["missing"]:
            await send(team, "system", "host", "feedback",
                       {"missing": team["missing"], "notice": "仅安排在场者，完整讨论待确认"})
        if not common_window(active):
            result.update(status="infeasible", reason="在场角色没有共同可用时间")
            return result
        plan = await ask(team, "host", "plan")
        result["after_communication"] = deepcopy(plan)

        # 4. 在草案之后注入故障。时间变更必须通过消息传给各个角色。
        if fault == "time_conflict":
            updated = next(p for p in active if p["id"] == "researcher")
            revised = common_window(active)[1] + 15
            updated["available"]["start"] = f"{revised // 60:02}:{revised % 60:02}"
            for receiver in recipients:
                await send(team, "researcher", receiver, "update", {"profile": updated})
        if fault == "forged_reference":
            plan["agenda"][0]["evidence_ids"] = ["nonexistent:999"]
            trace.emit("fault_injected", fault=fault, plan=deepcopy(plan))
        result["effective_profiles"] = deepcopy(active)

        # 5. 程序检查 + 质疑者评议 → 主持人修订；最多六轮。
        for round_number in range(1, config["max_rounds"] + 1):
            result["rounds"] = round_number
            errors = validate_plan(plan, active, corpus)
            reviewer = "host" if mode == "single" or "critic" in team["missing"] else "critic"
            await send(team, "host", reviewer, "proposal", {"plan": plan})
            review = await ask(team, reviewer, "review", {"validation_errors": errors})
            await send(team, reviewer, "host", "feedback", review)
            trace.emit("validation", round=round_number, errors=errors, plan=deepcopy(plan))
            if not errors:
                break
            result["repairs"].append({"errors": errors, "plan": deepcopy(plan)})
            await send(team, "system", "host", "feedback", {"validation_errors": errors})
            if round_number < config["max_rounds"]:
                plan = await ask(team, "host", "plan")
        else:
            result.update(status="invalid_plan", plan=plan, errors=errors)
            return result
        result["plan"] = plan

        # 6. 各自反思，其他人的反思不会自动出现在自己的上下文里。
        for who in recipients:
            await send(team, "host", who, "proposal", {"final_plan": plan})
        if mode == "multi_reflection":
            for who in recipients:
                state = team["states"][who]
                state["reflections"].append(
                    await reflect(state["observations"], team=team, who=who))

        # 7. 相同约束下的下一版方案；无反思组也做，避免多一次调用的混淆。
        result["next_repairs"] = []
        for attempt in range(2):
            next_plan = await ask(team, "host", "next_plan")
            next_errors = validate_plan(next_plan, active, corpus)
            if not next_errors:
                break
            result["next_repairs"].append({"errors": next_errors, "plan": next_plan})
            if attempt == 0:
                await send(team, "system", "host", "feedback",
                           {"next_plan_errors": next_errors})
        result.update(next_plan=next_plan, next_errors=next_errors,
                      status="degraded" if team["missing"] else "completed",
                      reflection_changed_output=next_plan != plan)
        if next_errors:
            result["status"] = "invalid_next_plan"
        return result
    except (RuntimeError, ValueError, KeyError, TypeError, TimeoutError) as error:
        reason = str(error)
        result.update(status="budget_exhausted" if "budget" in reason else "failed", reason=reason)
        return result
    finally:
        result["missing"] = team["missing"]
        result["messages"] = team["messages"]
        result["agents"] = team["states"]
        await team["runtime"].stop()
        await team["runtime"].close()


def run(payload, **context):
    """公共 CLI 同步入口。离线时不使用旧的通用 responses.json。"""
    config = context.get("config") or load_json(HERE / "config.json")
    model = context.get("model")
    if model is None:
        # 直接调用 run 时也使用同一工厂；已经传入的模型不被替换。
        model = make_model(config=config)
    model.max_calls = config["max_model_calls"]
    corpus = context.get("corpus")
    if corpus is None:
        corpus = load_jsonl(HERE / "data/corpus.jsonl")
    output = Path(context.get("artifact_dir", HERE / "artifacts"))
    trace = context.get("trace") or Trace(output / "run.jsonl")
    started = time.monotonic()
    result = asyncio.run(collaborate(payload, model, corpus, trace, config))
    offline = isinstance(model, OfflineModel)
    result["metrics"] = {
        "provider": "offline_rules" if offline else model.model_name,
        "model_calls": 0 if offline else model.calls,
        "simulated_calls": model.calls if offline else 0,
        "tool_calls": 0, "messages": len(result["messages"]),
        "seconds": round(time.monotonic() - started, 3),
        "token_usage": None if offline else getattr(model, "total_usage", {}),
    }
    save_json(output / "last_result.json", result)
    trace.emit("completed", status=result["status"], metrics=result["metrics"])
    return result
