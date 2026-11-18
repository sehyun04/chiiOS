# chiiOS 비서 봇의 머리. 대장과 이야기하고, 할 일·봇·기록은 홈 화면 서버에 부탁해서 만진다.
# 머리는 Anthropic API(비서 전용 키). 대화와 열쇠는 이 봇의 데이터 폴더(/data)에만 둔다.
import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import anthropic

import brief
import home
import work

# 평소 일(할 일 넣기, 상태 묻기)은 가볍고 싼 모델로 충분하다. 바꾸려면 compose.yaml 환경 변수로.
MODEL = os.environ.get("ASSIST_MODEL", "claude-haiku-5-5")
EFFORT = os.environ.get("ASSIST_EFFORT", "low")
SELF = "assistant"
# 대화가 길어질수록 매번 보내는 양이 늘어 값이 오른다. 최근 것만 기억한다.
HISTORY_TURNS = 20
# 도구를 부르고 결과를 읽는 왕복의 상한. 넘으면 끊고 그때까지 한 것만 말한다.
MAX_STEPS = 6
# 아침 보고 시각(지역 시각). 그 시각에 PC 가 꺼져 있었으면 켜진 뒤 처음 1분 안에 한다.
BRIEF_AT = os.environ.get("ASSIST_BRIEF_AT", "08:00")
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

지켜야 할 것
- 상태는 "지금 상태"와 도구 결과만 믿는다. 모르는 건 지어내지 말고 모른다고 한다.
- 니나브(loa-bot)는 Oracle 서버에서 도는 운영 봇과 디스코드 토큰이 같아서, 둘이 같이 켜지면 응답이 꼬인다. 그래서 깨우기 전 주의가 있는 봇의 start 는 바로 깨우지 않고 대장 화면에 확인 단추를 띄운다. 그때는 단추를 눌러 달라고 안내하고, 깨웠다고 말하지 않는다.
- 너 자신은 재울 수 없다. 재우고 싶다고 하면 봇 칸의 재우기 단추를 쓰라고 안내한다.
- 도구가 실패하면 실패했다고 그대로 말한다.
- 터미널 명령을 대신 칠 수는 없다. 필요하면 대장이 칠 명령을 알려 준다(1번 칸 터미널 탭)."""

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
]
# 스트리밍 중에 도구 입력도 생기는 대로 받는다. 대신 서버가 입력을 검사해 주지 않으므로 run_tool 에서 직접 본다.
for _t in TOOLS:
    _t["eager_input_streaming"] = True


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


def say(line):
    # docker logs 로 보이는 줄. 봇 칸의 기록 단추가 이걸 보여 준다. 대화 내용은 남기지 않는다.
    print(f"{datetime.now():%m-%d %H:%M:%S} {line}", file=sys.stdout, flush=True)


class Assistant:
    def __init__(self, data_dir):
        data = Path(data_dir)
        self.key_file = data / "anthropic-key"
        self.chat_file = data / "chat.jsonl"
        self.archive = data / "chat-archive"
        self.brief_file = data / "brief-last.json"
        self.busy = threading.Lock()
        self.file_lock = threading.Lock()
        self.brief_lock = threading.Lock()

    # 열쇠 ---------------------------------------------------------------

    def read_key(self):
        try:
            return self.key_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def save_key(self, key):
        key = str(key or "").strip()
        if not key.startswith("sk-ant-") or len(key) < 30 or any(c.isspace() for c in key):
            return False, "열쇠 모양이 아니야. sk-ant- 로 시작하는 API 키를 통째로 넣어 줘."
        # 저장하기 전에 한 번 맞춰 본다. 모델 정보 읽기는 토큰을 쓰지 않는다.
        try:
            anthropic.Anthropic(api_key=key, timeout=15.0, max_retries=1).models.retrieve(MODEL)
        except anthropic.AuthenticationError:
            return False, "열쇠가 안 맞아. 지운 키거나 잘못 복사한 것 같아."
        except anthropic.PermissionDeniedError:
            return False, f"이 열쇠로는 {MODEL} 을 못 써. 키의 작업 공간 설정을 봐 줘."
        except anthropic.APIConnectionError:
            return False, "Anthropic 에 안 닿아. 인터넷을 봐 줘."
        except anthropic.APIStatusError as e:
            return False, f"맞춰 보다 막혔어 ({e.status_code})."
        # 처음부터 600 으로 만든다. 쓰고 나서 바꾸면 그 사이 잠깐 남이 읽을 수 있다.
        fd = os.open(self.key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key + "\n")
        os.chmod(self.key_file, 0o600)
        say("열쇠 바꿈")
        return True, None

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
            "sdk": True,
            "hasKey": self.read_key() is not None,
            "model": MODEL,
            "busy": self.busy.locked(),
            "briefAt": BRIEF_AT,
            "turns": self.turns()[-60:],
        }

    # 맥락 ---------------------------------------------------------------

    def context(self):
        # 지난 턴은 글로만 넘긴다. 도구 호출 블록까지 다시 보내면 매번 보내는 양이 불고, 한 일은 한 줄 요약이면 충분하다.
        msgs = []
        for t in self.turns()[-HISTORY_TURNS:]:
            role = t.get("role")
            if role not in ("user", "assistant"):
                continue
            text = t.get("text") or ""
            if role == "assistant":
                done = t.get("tools") or []
                if done:
                    text = (text + "\n" if text else "") + "(한 일: " + "; ".join(done) + ")"
                if not text:
                    text = "(답하지 못함)"
            if not text:
                continue
            if not msgs and role == "assistant":
                # 대화가 아침 보고로 시작하면 앞에 묻는 말이 없다. 첫 메시지는 사용자 것이어야 해서 하나 채운다.
                msgs.append({"role": "user", "content": "(아침 보고를 열어 봄)"})
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n\n" + text
            else:
                msgs.append({"role": role, "content": text})
        return msgs

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

        return f"{name} 라는 도구는 없다", None, None, True

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
        key = self.read_key()
        if not key:
            return None
        try:
            r = anthropic.Anthropic(api_key=key, timeout=30.0, max_retries=1).messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM,
                output_config={"effort": EFFORT},
                messages=[{"role": "user", "content": (
                    "오늘 아침 보고 자료다.\n" + "\n".join(lines) +
                    "\n\n대장에게 건넬 첫마디를 한두 문장으로 써. 자료에 없는 숫자나 일은 만들지 말고, "
                    "오늘 먼저 볼 것 하나를 짚어. 인사말만 쓰지 말 것.")}],
            )
        except anthropic.APIError as e:
            say(f"아침 보고 한마디 실패 · {type(e).__name__}")
            return None
        if r.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        return text or None

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
        key = self.read_key()
        if not key:
            emit({"t": "error", "code": "key", "d": "하치와레 열쇠가 없어."})
            return
        self.append({"t": time.time(), "role": "user", "text": text})
        client = anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=2)
        system = [{"type": "text", "text": SYSTEM}, {"type": "text", "text": self.snapshot()}]
        messages = self.context()

        parts, chips, confirm = [], [], None
        usage = {"in": 0, "out": 0}
        error = code = None
        gap = False  # 도구를 다녀온 뒤 이어지는 말은 줄을 바꿔 붙인다.
        json_retries = 0
        step = 0
        started = time.time()
        while step < MAX_STEPS:
            step += 1
            try:
                with client.messages.stream(
                    model=MODEL,
                    max_tokens=16000,
                    system=system,
                    tools=TOOLS,
                    messages=messages,
                    output_config={"effort": EFFORT},
                ) as stream:
                    for event in stream:
                        if event.type == "text" and event.text:
                            if gap and parts:
                                parts.append("\n")
                                emit({"t": "text", "d": "\n"})
                            gap = False
                            parts.append(event.text)
                            emit({"t": "text", "d": event.text})
                    msg = stream.get_final_message()
                json_retries = 0
            except ValueError:
                # 도구 입력 JSON 을 아예 못 읽었다. 그 도구 호출은 끝나지 않아 답할 id 가 없으니 같은 턴을 다시 묻는다.
                json_retries += 1
                if json_retries > 2:
                    error, code = "도구 입력을 못 읽었어. 다시 말해 줘.", "bad"
                    break
                step -= 1
                continue
            except anthropic.AuthenticationError:
                error, code = "열쇠가 안 맞아. 새 열쇠를 넣어 줘.", "key"
                break
            except anthropic.PermissionDeniedError:
                error, code = f"이 열쇠로는 {MODEL} 을 못 써.", "key"
                break
            except anthropic.RateLimitError:
                error, code = "너무 자주 불렀어. 조금 있다가 다시 말해 줘.", "rate"
                break
            except anthropic.BadRequestError as e:
                m = str(getattr(e, "message", e))
                if "credit" in m.lower():
                    error, code = "크레딧이 바닥났어. Console 에서 충전해 줘.", "credit"
                elif "limit" in m.lower():
                    error, code = "이번 달 한도에 닿았어. Console 작업 공간 한도를 봐 줘.", "credit"
                else:
                    error, code = f"요청이 거절됐어: {m[:160]}", "bad"
                break
            except anthropic.APIStatusError as e:
                error, code = f"Anthropic 쪽이 지금 대답을 못 해 ({e.status_code}). 조금 뒤에 다시.", "server"
                break
            except anthropic.APIConnectionError:
                error, code = "Anthropic 에 안 닿아. 인터넷을 봐 줘.", "net"
                break

            usage["in"] += msg.usage.input_tokens
            usage["out"] += msg.usage.output_tokens
            if msg.stop_reason == "refusal":
                error, code = "그건 내가 도와줄 수 없는 일이야.", "refusal"
                break
            tool_uses = [b for b in msg.content if b.type == "tool_use"]
            if not tool_uses:
                if msg.stop_reason == "max_tokens":
                    error, code = "말이 너무 길어져서 끊겼어.", "long"
                break
            if msg.stop_reason == "max_tokens":
                # 잘린 도구 입력은 반쯤 채워진 채로 읽힌다. 그대로 실행하면 엉뚱한 일을 하니 멈춘다.
                error, code = "말이 너무 길어져서 끊겼어.", "long"
                break

            results = []
            for b in tool_uses:
                out, chip, conf, bad = self.run_tool(b.name, b.input)
                if chip:
                    chips.append(chip)
                    emit({"t": "tool", "d": chip, "bad": bad})
                if conf:
                    confirm = conf
                    emit({"t": "confirm", **conf})
                res = {"type": "tool_result", "tool_use_id": b.id, "content": out}
                if bad:
                    res["is_error"] = True
                results.append(res)
            # 생각 블록까지 응답을 통째로 돌려줘야 다음 단계에서 이어서 생각한다.
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": results})
            emit({"t": "refresh"})
            gap = True
        else:
            error, code = "할 일이 너무 많이 이어져서 여기서 멈췄어.", "steps"

        reply = "".join(parts).strip()
        if error:
            emit({"t": "error", "code": code, "d": error})
        self.append({
            "t": time.time(), "role": "assistant", "text": reply, "tools": chips,
            "confirm": confirm, "error": error, "code": code, "model": MODEL, "usage": usage,
        })
        say(f"대화 한 번 · {time.time() - started:.1f}초 · 토큰 {usage['in']}/{usage['out']} · 도구 {len(chips)}개"
            + (f" · 오류 {code}" if code else ""))
        emit({"t": "done"})
