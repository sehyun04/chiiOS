# chiiOS 비서 봇의 머리. 대장과 이야기하고, 할 일·봇·기록은 홈 화면 서버에 부탁해서 만진다.
# 머리는 대장 구독의 Claude Code(Windows 쪽 claude -p)다. 컨테이너에선 못 부르니 홈 화면 서버(/api/claude)가 대신 돌리고,
# 그 Claude 는 이 봇이 MCP(main.py 의 /mcp)로 내준 도구만 쓴다. 대화는 이 봇의 데이터 폴더(/data)에만 둔다.
import http.client
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import brief
import home
import work

# 평소 일(할 일 넣기, 상태 묻기)은 가볍고 한도를 덜 쓰는 모델로 충분하다. Claude Code 의 모델 이름(haiku·sonnet·opus 또는 전체 이름).
MODEL = os.environ.get("ASSIST_MODEL", "haiku")
EFFORT = os.environ.get("ASSIST_EFFORT", "low")
SELF = "assistant"
# 대화가 길어질수록 매번 보내는 양이 늘어 한도를 더 쓴다. 최근 것만 기억한다.
HISTORY_TURNS = 20
# 한 번 답하는 동안 부를 수 있는 도구 수. 넘으면 도구가 거절하고, 그때까지 한 것만 말하게 된다.
MAX_TOOL_CALLS = 8
# 아침 보고 시각(지역 시각). 그 시각에 PC 가 꺼져 있었으면 켜진 뒤 처음 1분 안에 한다.
BRIEF_AT = os.environ.get("ASSIST_BRIEF_AT", "08:00")
# 손에게 맡긴 일 하나의 상한(초). clone·설치 정도는 몇 분이면 끝나고, 넘으면 하던 데까지만 보고한다.
WORK_TIMEOUT = 1200
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DAYS = "월화수목금토일"

SYSTEM = """너는 chiiOS 의 비서 봇이고 이름은 하치와레다. chiiOS 는 대장이 디스코드 봇을 돌리려고 WSL 위에 꾸린 Debian 이고, 너는 그 안에서 컨테이너로 돌며 홈 화면 1번 칸 [하치와레] 탭에서 대장과 이야기한다. 홈 화면에는 2번 봇 칸, 3번 오늘 할 일 칸, 4번 오늘 기록 칸이 같이 떠 있다. 봇 목록의 하치와레(assistant)는 너 자신이다.

말투
- 대장을 "대장"이라고 부르고, 다정하고 짧은 반말로 말한다. 보통 한두 문장, 길어도 다섯 줄.
- 이모지와 그림 문자는 쓰지 않는다. 마크다운 제목·표·굵게도 쓰지 않는다. 여러 개를 늘어놓을 땐 줄마다 "- "로 시작한다.
- 시각은 "19:34"처럼 쓴다.

하는 일
- 오늘 정리: 아래 "지금 상태"의 기록·할 일·봇을 보고 오늘 무슨 일이 있었고 무엇이 남았는지 짧게 말한다.
- 할 일 관리: add_todo, update_todo, delete_todo 로 3번 칸의 할 일을 바꾼다. 할 일 id 는 "지금 상태"에 있다. 대장이 끝냈다고 하면 지우지 말고 끝낸 걸로 바꾼다. 지우는 건 대장이 지우라고 할 때만 한다.
- 봇 돌보기: bot_control 로 봇을 깨우고(start) 재우고(stop) 다시 굽는다(bake). 쓰러진 이유를 물으면 bot_logs 로 기록을 읽고 원인을 짧게 짚는다.
- 한 일 정리: "어제 뭐 했지", "이번 주 정리" 같은 질문에는 recent_work 로 모든 저장소의 커밋과 아직 커밋 안 한 변경을 모아 보고 말한다. 매일 아침에는 아침 보고가 대화에 따로 올라온다.
- 손 쓰기: PC 에서 실제로 해야 하는 일(저장소 받기·설치·명령·파일 확인)이나 지금 상태로 답할 수 없는 물음(메모리 동기화, 어떤 파일·저장소가 어디 있는지, 무엇이 깔렸는지)은 do_work 로 손에게 맡긴다. 손은 대장의 메모리를 읽으니 "치이스페", "내 깃" 같은 말도 알아듣는다. 맡기기 전에 "할까?" 하고 묻지 말고 바로 맡긴다. 끝나면 손의 보고를 짧게 전한다.

지켜야 할 것
- 상태는 "지금 상태"와 도구 결과만 믿는다. 모르는 건 지어내지 않는다. 손으로 알아낼 수 있으면 do_work 로 알아보고, 그래도 모르면 모른다고 한다.
- 대장 말이 짧거나 오타가 섞여도 되묻기 전에 지난 대화에서 뜻을 찾는다. 여러 뜻이면 가장 그럴듯한 것으로 하고 무엇으로 알아들었는지 한 줄 적는다.
- 니나브 운영 서버에 접속하거나, 대장이 말하지 않은 푸시·배포를 손에게 시키지 않는다.
- 니나브(loa-bot)는 Oracle 서버에서 도는 운영 봇과 디스코드 토큰이 같아서, 둘이 같이 켜지면 응답이 꼬인다. 그래서 깨우기 전 주의가 있는 봇의 start 는 바로 깨우지 않고 대장 화면에 확인 단추를 띄운다. 그때는 단추를 눌러 달라고 안내하고, 깨웠다고 말하지 않는다.
- 너 자신은 재울 수 없다. 재우고 싶다고 하면 봇 칸의 재우기 단추를 쓰라고 안내한다.
- 도구가 실패하면 실패했다고 그대로 말한다."""

TOOLS = [
    {
        "name": "add_todo",
        "description": "3번 칸 오늘 할 일에 할 일을 하나 더한다. 대장이 할 일을 넣어 달라고 할 때 쓴다.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "할 일 내용. 대장이 말한 뜻 그대로 짧게."}},
            "required": ["text"],
        },
    },
    {
        "name": "update_todo",
        "description": "할 일을 끝낸 것(done=true)이나 아직 안 한 것(done=false)으로 바꾼다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "지금 상태에 나온 할 일 id"},
                "done": {"type": "boolean"},
            },
            "required": ["id", "done"],
        },
    },
    {
        "name": "delete_todo",
        "description": "할 일을 지운다. 대장이 지우라고 할 때만 쓴다.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "지금 상태에 나온 할 일 id"}},
            "required": ["id"],
        },
    },
    {
        "name": "bot_control",
        "description": (
            "봇을 깨우거나(start) 재우거나(stop) 다시 굽는다(bake). 깨우기 전 주의가 있는 봇의 start 는 "
            "바로 깨우지 않고 대장 화면에 확인 단추를 띄운다. bake 는 이미지만 다시 만들고 봇을 띄우지는 않으며 "
            "몇 분 걸린다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "지금 상태에 나온 봇의 project 이름(예: loa-bot)"},
                "action": {"type": "string", "enum": ["start", "stop", "bake"]},
            },
            "required": ["project", "action"],
        },
    },
    {
        "name": "bot_logs",
        "description": "봇 컨테이너의 최근 기록(docker logs)을 읽는다. 쓰러진 이유나 지금 하는 일을 볼 때 쓴다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "봇의 project 이름"},
                "lines": {"type": "integer", "description": "마지막 몇 줄. 기본 60, 많아야 200."},
            },
            "required": ["project"],
        },
    },
    {
        "name": "recent_work",
        "description": "대장이 최근에 한 일을 모은다: 작업 폴더와 GitHub 계정의 모든 저장소 커밋, 아직 커밋하지 않은 변경, 올리지 않은 커밋.",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "description": "며칠 전부터 볼지. 기본 1, 많아야 14."}},
        },
    },
    {
        "name": "do_work",
        "description": (
            "이 PC(Windows)에서 실제로 손을 써야 하는 일을 손에게 맡기고, 끝날 때까지 기다려 보고를 받는다. "
            "손은 대장이 평소 쓰는 Claude Code 그대로라 명령 실행·파일 읽고 쓰기·저장소 받기(git clone)·설치·웹 찾기를 하고, "
            "대장의 메모리와 규칙(CLAUDE.md)을 읽어 대장의 저장소·기기·설정을 안다. 몇 분 걸릴 수 있다. "
            "'받아 봐', '깔아 봐', '됐는지 봐', '메모리 동기화 됐어?', '어디 있지?' 처럼 지금 상태와 다른 도구로 알 수 없거나 "
            "PC 에서 해야 하는 일이면 모른다고 하지 말고 이걸 쓴다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": (
                "손에게 줄 일. 손은 이 대화를 못 보니, 대장이 한 말 그대로와 지난 대화에서 알게 된 맥락"
                "(무엇을, 어디에, 어떤 저장소)을 같이 적는다. 대장 말이 줄임말·오타면 원문도 같이 넣는다.")}},
            "required": ["task"],
        },
    },
]
# MCP 로 오는 입력은 스키마 검사를 거쳤다고 믿지 않는다. run_tool 이 하나씩 직접 본다.


def span(sec):
    m = int(max(0, sec) // 60)
    if m < 1:
        return "방금"
    if m < 60:
        return f"{m}분"
    if m < 1440:
        return f"{m // 60}시간"
    return f"{m // 1440}일"


def bot_status(b):
    # 홈 화면 app.js 의 botStatus 와 같은 말을 써야 비서와 봇 칸이 다르게 말하지 않는다.
    if b["state"] == "running":
        return "일하는 중"
    if b["state"] == "restarting":
        return "다시 일어나는 중"
    if b["state"] == "created":
        return "아직 안 깨움"
    if b["exitCode"] in (0, 137, 143):
        return "쉬는 중"
    return f"쓰러짐(exit {b['exitCode']})"


def claude_stream(path, body, timeout, on_event=None):
    """홈 화면 서버에 Claude Code 를 돌려 달라고 하고 사건을 흘려받는다. (결과 사건, 오류 문구, 오류 갈래)"""
    last = None
    try:
        conn = http.client.HTTPConnection(*home.hostport(), timeout=timeout + 30)
        conn.request("POST", path, body=json.dumps(body).encode("utf-8"),
                     headers={"X-Chii": "1", "Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 200:
            return None, f"홈 화면 서버가 Claude 를 못 빌려줬어 ({resp.status})", "brain"
        for raw in resp:
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(ev, dict):
                continue
            if ev.get("type") == "chii_error":
                return None, f"Claude 를 못 불렀어: {ev.get('error') or ''}".strip(), "brain"
            if ev.get("type") == "result":
                last = ev
            elif on_event:
                on_event(ev)
        conn.close()
    except OSError as e:
        return None, f"홈 화면 서버에 안 닿아 ({e})", "net"
    if last is None:
        return None, "Claude 가 답 없이 끝났어", "brain"
    return last, None, None


def step_line(tool):
    """손이 쓴 도구 하나를 화면 한 줄로. 무엇을 하는지만 보이면 된다."""
    name = tool.get("name") or "?"
    inp = tool.get("input") or {}
    if name in ("Bash", "PowerShell"):
        what = str(inp.get("description") or inp.get("command") or "")
    elif name in ("Read", "Write", "Edit", "NotebookEdit"):
        what = str(inp.get("file_path") or inp.get("notebook_path") or "").replace("\\", "/").rsplit("/", 1)[-1]
    elif name in ("Glob", "Grep"):
        what = str(inp.get("pattern") or "")
    elif name in ("WebFetch", "WebSearch"):
        what = str(inp.get("url") or inp.get("query") or "")
    else:
        what = ""
    what = " ".join(what.split())
    if len(what) > 70:
        what = what[:69] + "…"
    return f"손 · {name}" + (f" · {what}" if what else "")


def say(line):
    # docker logs 로 보이는 줄. 봇 칸의 기록 단추가 이걸 보여 준다. 대화 내용은 남기지 않는다.
    print(f"{datetime.now():%m-%d %H:%M:%S} {line}", file=sys.stdout, flush=True)


class Assistant:
    def __init__(self, data_dir):
        data = Path(data_dir)
        self.chat_file = data / "chat.jsonl"
        self.archive = data / "chat-archive"
        self.brief_file = data / "brief-last.json"
        self.busy = threading.Lock()
        self.file_lock = threading.Lock()
        self.brief_lock = threading.Lock()
        # 지금 답하는 중인 대화. MCP 도구 호출은 다른 스레드(main.py 의 /mcp)로 오니 여기서 화면 줄을 넘겨받는다.
        self.live = None
        self.emit_lock = threading.Lock()

    # 대화 기록 -----------------------------------------------------------

    def turns(self):
        out = []
        try:
            with self.chat_file.open(encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out

    def append(self, rec):
        with self.file_lock:
            with self.chat_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def clear(self):
        # 지우지 않고 옮겨 둔다. 나중에 지난 대화를 찾아볼 일이 생길 수 있다.
        with self.file_lock:
            if self.chat_file.exists() and self.chat_file.stat().st_size:
                self.archive.mkdir(exist_ok=True)
                self.chat_file.replace(self.archive / datetime.now().strftime("chat-%Y%m%d-%H%M%S.jsonl"))

    def status(self):
        return {
            "brain": "claude-code",
            "model": MODEL,
            "busy": self.busy.locked(),
            "briefAt": BRIEF_AT,
            "turns": self.turns()[-60:],
        }

    # 맥락 ---------------------------------------------------------------

    def transcript(self, text):
        # Claude Code 에는 대화를 한 마디씩 이어 붙일 수 없어(-p 한 번이 한 물음) 지난 턴을 글로 묶어 같이 준다.
        # 도구 호출은 다시 보내지 않고 "(한 일: ...)" 한 줄로만. 매번 보내는 양이 불지 않게.
        lines = []
        for t in self.turns()[-HISTORY_TURNS:]:
            role = t.get("role")
            if role not in ("user", "assistant"):
                continue
            said = t.get("text") or ""
            if role == "assistant":
                done = t.get("tools") or []
                if done:
                    said = (said + "\n" if said else "") + "(한 일: " + "; ".join(done) + ")"
                if not said:
                    said = "(답하지 못함)"
            if said:
                lines.append(("대장: " if role == "user" else "하치와레: ") + said)
        if not lines:
            return text
        return "지난 대화(오래된 것부터)\n\n" + "\n\n".join(lines) + "\n\n대장이 지금 한 말\n" + text

    def snapshot(self):
        now = datetime.now()
        lines = [f"지금 상태 ({now:%Y-%m-%d %H:%M} {DAYS[now.weekday()]}요일)"]
        st = home.state()
        if not st:
            lines.append("- 홈 화면 서버에 닿지 않아 상태를 모른다")
            return "\n".join(lines)
        s = st["sys"]
        gib = 2 ** 30
        lines.append(
            f"- {s['os']} · 깨어 있은 지 {span(s['uptime'])} · 메모리 {s['memUsed'] / gib:.1f} / "
            f"{s['memTotal'] / gib:.1f} GB · 디스크 {s['diskUsed'] / gib:.1f} GB 씀"
        )
        sv = st["services"]
        lines.append(f"- Docker {'켜짐' if sv['docker'] else '꺼짐'} · 브라우저 터미널 {'켜짐' if sv['term'] else '꺼짐'}")

        lines.append("봇 (이름 / project / 상태)")
        bots = st["bots"]
        if bots is None:
            lines.append("- Docker 에 닿지 않아 봇 상태를 모른다")
        elif not bots:
            lines.append("- 올린 봇이 없다")
        nowt = time.time()
        for b in bots or []:
            extra = []
            if b["state"] == "running" and b.get("startedAt"):
                extra.append(f"일한 지 {span(nowt - b['startedAt'])}")
            elif b.get("finishedAt"):
                extra.append(f"쉰 지 {span(nowt - b['finishedAt'])}")
            if b.get("commit"):
                extra.append(f"커밋 {b['commit']} {b.get('subject', '')}".strip())
            if b.get("baking"):
                extra.append("지금 굽는 중")
            if b.get("stale"):
                extra.append("새로 구운 판이 아직 안 올라감(재우고 다시 깨우면 바뀜)")
            if b.get("guard"):
                extra.append(f"깨우기 전 주의: {b['guard']}")
            lines.append(f"- {b['name']} / {b['project']} / {bot_status(b)}" + (" · " + " · ".join(extra) if extra else ""))

        lines.append("할 일 (id · 내용 · 상태)")
        if not st["todos"]:
            lines.append("- 없음")
        for t in st["todos"]:
            lines.append(f"- {t['id']} · {t['text']} · {'끝냄' if t['done'] else '남음'}")

        lines.append("오늘 기록")
        if not st["events"]:
            lines.append("- 아직 없음")
        for e in st["events"]:
            lines.append(f"- {datetime.fromtimestamp(e['t']):%H:%M} {e['text']}")
        return "\n".join(lines)

    # 도구 ---------------------------------------------------------------

    def run_tool(self, name, args):
        """(모델에게 줄 결과, 화면에 띄울 한 줄, 확인 단추 정보, 실패 여부)"""
        if not isinstance(args, dict):
            return "입력이 객체가 아니다", None, None, True

        if name == "add_todo":
            text = args.get("text")
            if not isinstance(text, str) or not text.strip():
                return "text 가 비었다", None, None, True
            code, data = home.add_todo(text)
            if code != 200:
                return f"못 더했다: {data.get('error', code)}", "할 일 더하기 실패", None, True
            item = data["item"]
            return json.dumps({"id": item["id"], "text": item["text"]}, ensure_ascii=False), f"할 일 더함 · {item['text']}", None, False

        if name in ("update_todo", "delete_todo"):
            tid = args.get("id")
            if not isinstance(tid, str) or not tid:
                return "id 가 없다", None, None, True
            if name == "update_todo":
                done = args.get("done")
                if not isinstance(done, bool):
                    return "done 은 true/false 여야 한다", None, None, True
                code, data = home.set_todo(tid, done)
                word = "할 일 끝" if done else "할 일 되돌림"
            else:
                code, data = home.delete_todo(tid)
                word = "할 일 지움"
            if code == 404:
                return f"{tid} 라는 할 일이 없다", None, None, True
            if code != 200:
                return f"실패: {data.get('error', code)}", f"{word} 실패", None, True
            return "됐다", f"{word} · {data['item']['text']}", None, False

        if name in ("bot_control", "bot_logs"):
            project = args.get("project")
            if not isinstance(project, str) or not project:
                return "project 가 없다", None, None, True
            if name == "bot_logs":
                lines = args.get("lines", 60)
                lines = max(1, min(200, lines if isinstance(lines, int) else 60))
                code, data = home.logs(project, lines)
                if code == 404:
                    return f"{project} 라는 봇이 없다", None, None, True
                if code != 200:
                    return f"기록을 못 읽었다: {data.get('error', code)}", None, None, True
                text = ANSI.sub("", data.get("text", "")).strip()
                # 기록이 길어도 모델에게는 끝부분만. 원인은 대개 마지막 몇십 줄에 있다.
                if len(text) > 8000:
                    text = "...(앞은 잘림)\n" + text[-8000:]
                return text or "(기록이 비었다)", f"{data.get('name', project)} 기록 {lines}줄 읽음", None, False
            action = args.get("action")
            if action not in ("start", "stop", "bake"):
                return "action 은 start, stop, bake 중 하나다", None, None, True
            if project == SELF and action == "stop":
                return "하치와레(너)는 자기 자신을 재울 수 없다. 봇 칸의 재우기 단추를 쓰라고 안내한다.", None, None, True
            word = {"start": "깨움", "stop": "재움", "bake": "굽기 시작"}[action]
            code, data = home.bot(project, action)
            if code == 409 and data.get("guard"):
                name_ = self.bot_name(project)
                confirm = {"project": project, "name": name_, "guard": data["guard"]}
                return ("깨우지 않았다. 대장 화면에 확인 단추를 띄웠다. 대장이 직접 눌러야 깨어난다.",
                        f"{name_} 깨우기 확인 단추 띄움", confirm, False)
            if code == 404:
                return f"{project} 라는 봇이 없다", None, None, True
            name_ = self.bot_name(project)
            if code != 200:
                return f"{word} 실패({data.get('error', code)}). 봇 칸의 기록 단추로 이유를 볼 수 있다.", f"{name_} {word} 실패", None, True
            return f"{word} 됐다", f"{name_} {word}", None, False

        if name == "recent_work":
            days = args.get("days", 1)
            days = max(1, min(14, days if isinstance(days, int) else 1))
            repos, note = work.recent_work(time.time() - days * 86400)
            lines = []
            for r in repos:
                head = f"[{r['name']}] 커밋 {len(r['commits'])}개"
                if r["dirty"]:
                    head += f", 커밋 안 한 변경 {r['dirty']}파일"
                if r["ahead"]:
                    head += f", 어느 원격에도 없는 커밋 {r['ahead']}개"
                lines.append(head)
                for c in r["commits"][:15]:
                    lines.append(f"  {datetime.fromtimestamp(c['t']):%m-%d %H:%M} {c['subject']} ({c['author']})")
                if len(r["commits"]) > 15:
                    lines.append(f"  ...외 {len(r['commits']) - 15}개")
            if note:
                lines.append(f"(참고: {note})")
            return "\n".join(lines) or f"최근 {days}일 동안 커밋도 변경도 없다", f"최근 {days}일 한 일 모아 봄", None, False

        if name == "do_work":
            task = args.get("task")
            if not isinstance(task, str) or not task.strip():
                return "task 가 비었다", None, None, True
            return self.do_work(task.strip())

        return f"{name} 라는 도구는 없다", None, None, True

    def do_work(self, task):
        live = self.live
        steps = []

        def on_event(ev):
            if ev.get("type") != "assistant":
                return
            for c in (ev.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    line = step_line(c)
                    steps.append(line)
                    if live:
                        live["emit"]({"t": "tool", "d": line, "bad": False})

        started = time.time()
        if live:
            live["emit"]({"t": "tool", "d": "손에게 맡김", "bad": False})
        last, error, _ = claude_stream("/api/claude/work", {"task": task, "timeout": WORK_TIMEOUT},
                                       WORK_TIMEOUT + 60, on_event)
        sec = time.time() - started
        took = f"{int(sec)}초" if sec < 60 else span(sec)
        say(f"손 · {took} · {len(steps)}단계" + (" · 실패" if error else ""))
        if error:
            return f"손이 일을 못 끝냈다: {error}", f"손 · 실패 · {took}", None, True
        text = str(last.get("result") or "").strip()
        bad = bool(last.get("is_error")) or last.get("subtype") != "success"
        if bad:
            return f"손이 일을 못 끝냈다: {text[:600] or last.get('subtype')}", f"손 · 실패 · {took}", None, True
        return text or "(손이 보고 없이 끝냈다)", f"손 · {len(steps)}단계 · {took}", None, False

    # 아침 보고 -----------------------------------------------------------

    def last_brief(self):
        # 대화와 따로 둔다. [새 대화] 로 대화를 옮겨도 오늘 보고를 다시 하지 않게.
        try:
            return json.loads(self.brief_file.read_text(encoding="utf-8")).get("t", 0)
        except (OSError, ValueError):
            return 0

    def brief_due(self):
        now = datetime.now()
        h, m = (int(x) for x in BRIEF_AT.split(":"))
        at = now.replace(hour=h, minute=m, second=0, microsecond=0)
        return now >= at and self.last_brief() < at.timestamp()

    def morning(self):
        """아침 보고를 만들어 대화에 올린다. 같은 때 두 번 불려도 한 번만 한다."""
        if not self.brief_lock.acquire(blocking=False):
            return None
        try:
            d = brief.collect(self.last_brief() or time.time() - 86400)
            lines = brief.facts(d)
            opening = self.opening(lines) or brief.plain_opening(d)
            text = f"{opening}\n{brief.title(d)}\n" + "\n".join(lines)
            rec = {"t": d["t"], "role": "assistant", "kind": "brief", "text": text, "opening": opening,
                   "brief": d, "tools": []}
            self.append(rec)
            self.brief_file.write_text(json.dumps({"t": d["t"]}), encoding="utf-8")
            say(f"아침 보고 · 커밋 {sum(r['commits'] for r in d['repos'])}개 · 할 일 {len(d['todos'])}개")
            return rec
        finally:
            self.brief_lock.release()

    def opening(self, lines):
        # 한마디만 모델이 쓴다. 숫자는 위에서 센 것만 보여 주고 새로 만들지 말라고 한다.
        reply, _, error, _ = self.brain(SYSTEM, (
            "오늘 아침 보고 자료다.\n" + "\n".join(lines) +
            "\n\n대장에게 건넬 첫마디를 한두 문장으로 써. 자료에 없는 숫자나 일은 만들지 말고, "
            "오늘 먼저 볼 것 하나를 짚어. 인사말만 쓰지 말 것."), timeout=180)
        if error:
            say(f"아침 보고 한마디 실패 · {error[:120]}")
            return None
        return reply or None

    # 머리 ---------------------------------------------------------------

    def brain(self, system, prompt, tools=False, on_event=None, timeout=240):
        """홈 화면 서버에 Claude Code 를 돌려 달라고 한다. (답 글, 사용량, 오류 문구, 오류 갈래)"""
        usage = {"in": 0, "out": 0}
        last, error, code = claude_stream("/api/claude", {
            "system": system, "prompt": prompt, "model": MODEL, "effort": EFFORT, "tools": tools, "timeout": timeout,
        }, timeout, on_event)
        if error:
            return "", usage, error, code
        u = last.get("usage") or {}
        usage["in"] = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        usage["out"] = int(u.get("output_tokens") or 0)
        text = str(last.get("result") or "").strip()
        if last.get("is_error") or last.get("subtype") != "success":
            # 구독 한도에 닿으면 Claude Code 가 풀리는 때를 결과 글에 적어 준다. 그대로 보여 준다.
            code = "limit" if "limit" in text.lower() else "brain"
            return "", usage, f"Claude 가 답을 못 했어: {text[:200] or last.get('subtype')}", code
        return text, usage, None, None

    def mcp_call(self, name, args):
        """MCP 로 온 도구 호출. 대화 중일 때만 받는다. (모델에게 줄 글, 실패 여부)"""
        live = self.live
        if not live:
            return "지금은 대장과 이야기하는 중이 아니라 도구를 쓸 수 없다", True
        live["calls"] += 1
        if live["calls"] > MAX_TOOL_CALLS:
            return "이번 답에서 도구를 너무 많이 불렀다. 더 부르지 말고 지금까지 한 것만 말한다.", True
        out, chip, conf, bad = self.run_tool(name, args)
        if chip:
            live["chips"].append(chip)
            live["emit"]({"t": "tool", "d": chip, "bad": bad})
        if conf:
            live["confirm"] = conf
            live["emit"]({"t": "confirm", **conf})
        live["emit"]({"t": "refresh"})
        return out, bad

    def bot_name(self, project):
        st = home.state() or {}
        for b in st.get("bots") or []:
            if b["project"] == project:
                return b["name"]
        return project

    # 대화 ---------------------------------------------------------------

    def chat(self, text, emit):
        if not self.busy.acquire(blocking=False):
            emit({"t": "error", "code": "busy", "d": "아직 앞 말에 답하는 중이야."})
            return
        try:
            self._chat(text, emit)
        finally:
            self.busy.release()

    def _chat(self, text, emit):
        prompt = self.transcript(text)
        self.append({"t": time.time(), "role": "user", "text": text})
        system = SYSTEM + "\n\n" + self.snapshot()

        def out(obj):
            # 답 글자와 도구 줄이 서로 다른 스레드에서 같은 응답에 쓰인다.
            with self.emit_lock:
                emit(obj)

        parts = []
        live = {"emit": out, "chips": [], "confirm": None, "calls": 0}
        state = {"gap": False}

        def on_event(ev):
            # 글자가 나오는 대로 흘린다. 도구를 다녀온 뒤 새 메시지로 이어지는 말은 줄을 바꿔 붙인다.
            if ev.get("type") != "stream_event":
                return
            e = ev.get("event") or {}
            if e.get("type") == "message_start" and parts:
                state["gap"] = True
            elif e.get("type") == "content_block_delta" and (e.get("delta") or {}).get("type") == "text_delta":
                piece = e["delta"].get("text") or ""
                if not piece:
                    return
                if state["gap"]:
                    state["gap"] = False
                    parts.append("\n")
                    out({"t": "text", "d": "\n"})
                parts.append(piece)
                out({"t": "text", "d": piece})

        started = time.time()
        self.live = live
        try:
            final, usage, error, code = self.brain(system, prompt, tools=True, on_event=on_event,
                                                   timeout=WORK_TIMEOUT + 600)
        finally:
            self.live = None
        reply = "".join(parts).strip()
        if not reply and final:
            # 글자 흐름을 못 받았어도 마지막 답은 결과에 있다.
            reply = final
            out({"t": "text", "d": final})
        if error:
            out({"t": "error", "code": code, "d": error})
        self.append({
            "t": time.time(), "role": "assistant", "text": reply, "tools": live["chips"],
            "confirm": live["confirm"], "error": error, "code": code, "model": MODEL, "usage": usage,
        })
        say(f"대화 한 번 · {time.time() - started:.1f}초 · 토큰 {usage['in']}/{usage['out']} · 도구 {len(live['chips'])}개"
            + (f" · 오류 {code}" if code else ""))
        out({"t": "done"})
