"""计划的时间、证据和约束检查；不依赖 AutoGen 或模型。"""
from datetime import date, datetime


def minutes(value):
    """19:30 → 当天第 1170 分钟。"""
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def common_window(profiles):
    dates = {p["available"]["date"] for p in profiles}
    start = max(minutes(p["available"]["start"]) for p in profiles)
    end = min(minutes(p["available"]["end"]) for p in profiles)
    return (next(iter(dates)), start, end) if len(dates) == 1 and end > start else None


def validate_plan(plan, profiles, corpus):
    """P4-04：代码检查约束，不让模型自己宣布计划正确。"""
    errors = []
    try:
        date.fromisoformat(plan["date"])
        start, end = minutes(plan["start"]), minutes(plan["end"])
        if end <= start:
            errors.append("结束时间必须晚于开始时间")
        for profile in profiles:
            available = profile["available"]
            if (plan["date"] != available["date"]
                    or start < minutes(available["start"])
                    or end > minutes(available["end"])):
                errors.append(f"时间不在 {profile['id']} 的可用范围内")
        owners = {p["id"] for p in profiles}
        topics = {t for p in profiles for t in p["known_topics"]}
        evidence = {f"{r['doc_id']}:{r['paragraph_id']}": r["text"] for r in corpus}
        agenda = plan["agenda"]
        if not isinstance(agenda, list) or not agenda:
            return ["议程必须是非空列表"]
        total = 0
        for item in agenda:
            if item["topic"] not in ("ReAct", "Toolformer", "MemGPT"):
                errors.append("topic 只能是 ReAct、Toolformer 或 MemGPT")
                continue
            if item["owner"] not in owners:
                errors.append("分工包含未知或缺席角色")
            if type(item["minutes"]) is not int or item["minutes"] <= 0:
                errors.append("每项时长必须为正整数")
            else:
                total += item["minutes"]
            ids = item["evidence_ids"]
            if not isinstance(ids, list) or not ids:
                errors.append("每项议程必须提供证据 ID")
                continue
            for ref in ids:
                if not isinstance(ref, str) or ref not in evidence:
                    errors.append(f"不存在的证据 ID：{ref}")
                elif item["topic"].lower() not in evidence[ref].lower():
                    errors.append(f"证据未提及议程主题：{ref}")
        if total > end - start:
            errors.append("议程总时长超过会议时长")
        if not topics.issubset({a["topic"] for a in agenda}):
            errors.append("议程未覆盖所有在场角色的主题")
        if not owners.issubset({a["owner"] for a in agenda}):
            errors.append("未给所有在场角色分工")
    except (KeyError, TypeError, ValueError):
        errors.append("计划格式错误：需要 date/start/end/agenda 及合法时间")
    return errors


def select_evidence(profile, corpus):
    """每个主题选一段笔记。这章练通信，不重新实现 P3 的 RAG。"""
    selected = []
    for topic in profile["known_topics"]:
        matches = [r for r in corpus if topic.lower() in r["text"].lower()
                   and len(r["text"]) > 50]
        if matches:
            record = min(matches, key=lambda r: len(r["text"]))
            selected.append({"id": f"{record['doc_id']}:{record['paragraph_id']}",
                             "text": record["text"]})
    return selected


