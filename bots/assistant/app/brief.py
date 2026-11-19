# 아침 보고. 숫자(봇 상태, 할 일, 커밋 수)는 여기서 세고, 비서는 맨 위 한마디만 쓴다.
# 비서봇을 오래 쓴 사람들의 공통점: 모으기는 스크립트, 말은 AI. AI 가 숫자까지 쓰면 틀린 숫자를 믿게 된다.
import time
from datetime import datetime

import home
import work

DAYS = "월화수목금토일"
# 보고 사이가 길어도(노트북을 며칠 끈 경우) 사흘치까지만 모은다. 그 이상은 아침에 읽을 양이 아니다.
MAX_SPAN = 3 * 86400


def status_word(b):
    if b["state"] == "running":
        return "일하는 중"
    if b["state"] == "restarting":
        return "다시 일어나는 중"
    if b["state"] == "created":
        return "아직 안 깨움"
    if b["exitCode"] in (0, 137, 143):
        return "쉬는 중"
    return "쓰러짐"


def collect(since):
    now = time.time()
    since = max(since, now - MAX_SPAN)
    st = home.state() or {}
    bots = [{"name": b["name"], "status": status_word(b)} for b in st.get("bots") or []]
    events = [e for e in st.get("events") or [] if e["t"] >= since]
    trouble = [e["text"] for e in events if e.get("kind") in ("crash", "bakefail")]
    todos = [t["text"] for t in st.get("todos") or [] if not t["done"]]
    repos, note = work.recent_work(since)
    run = (st.get("night") or {}).get("run") or {}
    night = {"todo": (run.get("todo") or {}).get("text") or "", "status": run.get("status"),
             "commits": len(run.get("commits") or []), "repo": run.get("repo"), "error": run.get("error")} if run else None
    return {
        "t": now,
        "since": since,
        "bots": bots,
        "homeOk": bool(st),
        "trouble": trouble,
        "todos": todos,
        "repos": [{
            "name": r["name"],
            "commits": len(r["commits"]),
            "subjects": [c["subject"] for c in r["commits"][:5]],
            "dirty": r["dirty"],
            "ahead": r["ahead"] or 0,
        } for r in repos],
        "note": note,
        "night": night,
    }


def facts(d):
    """보고의 사실 줄. 화면 카드와 모델 맥락이 같은 내용을 본다."""
    lines = []
    if not d["homeOk"]:
        lines.append("- 홈 화면 서버에 닿지 않아 봇과 할 일은 못 봤다")
    else:
        bots = ", ".join(f"{b['name']} {b['status']}" for b in d["bots"]) or "올린 봇 없음"
        lines.append(f"- 봇: {bots}. " + (f"그동안 문제: {'; '.join(d['trouble'])}" if d["trouble"] else "그동안 쓰러진 봇 없음"))
        lines.append(f"- 할 일 {len(d['todos'])}개 남음" + (": " + ", ".join(d["todos"]) if d["todos"] else ""))
    n = d.get("night")
    if n:
        word = {"done": f"{n['todo']} 해서 {n['repo']} 에 커밋 {n['commits']}개 올려 둠(합칠지 대장이 정함)",
                "nothing": f"{n['todo']} 봤지만 고친 것 없음", "failed": f"{n['todo']} 못 끝냄 ({n.get('error') or ''})",
                "none": "혼자 해 둘 만한 할 일이 없었음", "running": f"{n['todo']} 하는 중"}.get(n["status"], "")
        if word:
            lines.append(f"- 하치와레 밤 작업: {word}")
    total = sum(r["commits"] for r in d["repos"])
    if total:
        per = ", ".join(f"{r['name']} {r['commits']}" for r in d["repos"] if r["commits"])
        lines.append(f"- 지난 보고 뒤로 커밋 {total}개 ({per})")
    else:
        lines.append("- 지난 보고 뒤로 커밋 없음")
    dirty = [f"{r['name']} {r['dirty']}파일" for r in d["repos"] if r["dirty"]]
    if dirty:
        lines.append(f"- 커밋 안 한 변경: {', '.join(dirty)}")
    ahead = [f"{r['name']} {r['ahead']}개" for r in d["repos"] if r["ahead"]]
    if ahead:
        lines.append(f"- 어느 원격에도 없는 커밋(백업 안 됨): {', '.join(ahead)}")
    return lines


def title(d):
    t = datetime.fromtimestamp(d["t"])
    return f"아침 보고 ({t.month}월 {t.day}일 {DAYS[t.weekday()]}요일)"


def plain_opening(d):
    if d["trouble"]:
        return "대장, 그동안 쓰러진 봇이 있어. 먼저 봐 줘."
    if d["todos"]:
        return f"대장, 좋은 아침. 오늘 할 일 {len(d['todos'])}개 남았어."
    return "대장, 좋은 아침. 오늘은 걸리는 게 없어."
