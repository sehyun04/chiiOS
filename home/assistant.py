# chiiOS 비서. 홈 화면 1번 칸 [비서] 탭에서 대장과 이야기하고, 할 일·봇·기록을 대신 만진다.
# 머리는 Anthropic API(비서 전용 키). 도구는 홈 화면 서버(server.py)의 함수를 그대로 빌려 쓴다.
# 화면 단추와 비서가 같은 함수를 지나가야 기록·확인 창 규칙이 한 곳에서만 정해진다.
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

try:
    import anthropic
except ImportError:
    # venv 없이 시스템 python 으로 돌 때. 홈 화면은 살리고 비서만 끈다.
    anthropic = None

# 평소 일(할 일 넣기, 상태 묻기)은 가볍고 싼 모델로 충분하다. 바꾸려면 chii-home 환경 변수로.
MODEL = os.environ.get("CHII_ASSIST_MODEL", "claude-haiku-5-5")
EFFORT = os.environ.get("CHII_ASSIST_EFFORT", "low")
KEY_FILE = Path(os.environ.get("CHII_ASSIST_KEY", str(Path.home() / ".config/chiios/anthropic-key")))
# 대화가 길어질수록 매번 보내는 양이 늘어 값이 오른다. 오늘 일을 다루는 비서라 최근 것만 기억한다.
HISTORY_TURNS = 20
# 도구를 부르고 결과를 읽는 왕복의 상한. 넘으면 끊고 그때까지 한 것만 말한다.
MAX_STEPS = 6
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
DAYS = "월화수목금토일"

SYSTEM = """너는 chiiOS 의 비서다. chiiOS 는 대장이 디스코드 봇을 돌리려고 WSL 위에 꾸린 Debian 이고, 너는 그 홈 화면 1번 칸에서 대장과 이야기한다. 홈 화면에는 2번 봇 칸, 3번 오늘 할 일 칸, 4번 오늘 기록 칸이 같이 떠 있다.

말투
- 대장을 "대장"이라고 부르고, 다정하고 짧은 반말로 말한다. 보통 한두 문장, 길어도 다섯 줄.
- 이모지와 그림 문자는 쓰지 않는다. 마크다운 제목·표·굵게도 쓰지 않는다. 여러 개를 늘어놓을 땐 줄마다 "- "로 시작한다.
- 시각은 "19:34"처럼 쓴다.

하는 일
- 오늘 정리: 아래 "지금 상태"의 기록·할 일·봇을 보고 오늘 무슨 일이 있었고 무엇이 남았는지 짧게 말한다.
- 할 일 관리: add_todo, update_todo, delete_todo 로 3번 칸의 할 일을 바꾼다. 할 일 id 는 "지금 상태"에 있다. 대장이 끝냈다고 하면 지우지 말고 끝낸 걸로 바꾼다. 지우는 건 대장이 지우라고 할 때만 한다.
- 봇 돌보기: bot_control 로 봇을 깨우고(start) 재우고(stop) 다시 굽는다(bake). 쓰러진 이유를 물으면 bot_logs 로 기록을 읽고 원인을 짧게 짚는다.

지켜야 할 것
- 상태는 "지금 상태"와 도구 결과만 믿는다. 모르는 건 지어내지 말고 모른다고 한다.
- 니나브(loa-bot)는 Oracle 서버에서 도는 운영 봇과 디스코드 토큰이 같아서, 둘이 같이 켜지면 응답이 꼬인다. 그래서 깨우기 전 주의가 있는 봇의 start 는 바로 깨우지 않고 대장 화면에 확인 단추를 띄운다. 그때는 단추를 눌러 달라고 안내하고, 깨웠다고 말하지 않는다.
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
            "바로 깨우지 않고 대장 화면에 확인 단추를 띄운다. bake 는 코드를 새로 가져와 이미지만 다시 만들고 "
            "봇을 띄우지는 않으며 몇 분 걸린다."
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
]
# 스트리밍 중에 도구 입력도 생기는 대로 받는다. 대신 서버가 입력을 검사해 주지 않으므로 run_tool 에서 직접 본다.
for _t in TOOLS:
    _t["eager_input_streaming"] = True


@dataclass
class World:
    system_info: Callable
    services: Callable
    bots: Callable
    find_bot: Callable
    todos: Callable
    events: Callable
    add_todo: Callable
    change_todo: Callable
    bot_act: Callable
    bot_logs: Callable


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


def read_key():
    try:
        return KEY_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


class Assistant:
    def __init__(self, state_dir, world):
        self.world = world
        self.chat_file = Path(state_dir) / "chat.jsonl"
        self.archive = Path(state_dir) / "chat-archive"
        self.busy = threading.Lock()
        self.file_lock = threading.Lock()

    # 기록 ---------------------------------------------------------------

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
            self.chat_file.parent.mkdir(parents=True, exist_ok=True)
            with self.chat_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def clear(self):
        # 지우지 않고 옮겨 둔다. 나중에 비서가 지난 대화를 찾아볼 일이 생길 수 있다.
        with self.file_lock:
            if self.chat_file.exists() and self.chat_file.stat().st_size:
                self.archive.mkdir(parents=True, exist_ok=True)
                self.chat_file.replace(self.archive / datetime.now().strftime("chat-%Y%m%d-%H%M%S.jsonl"))

    def status(self):
        return {
            "sdk": anthropic is not None,
            "hasKey": read_key() is not None,
            "model": MODEL,
            "busy": self.busy.locked(),
            "turns": self.turns()[-60:],
        }

    def save_key(self, key):
        key = str(key or "").strip()
        if not key.startswith("sk-ant-") or len(key) < 30 or any(c.isspace() for c in key):
            return False, "열쇠 모양이 아니야. sk-ant- 로 시작하는 API 키를 통째로 넣어 줘."
        if anthropic is None:
            return False, "비서 부품(anthropic SDK)이 없어. setup.sh 를 다시 돌려 줘."
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
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(KEY_FILE.parent, 0o700)
        # 처음부터 600 으로 만든다. 쓰고 나서 바꾸면 그 사이 잠깐 남이 읽을 수 있다.
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(key + "\n")
        os.chmod(KEY_FILE, 0o600)
        return True, None

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
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n\n" + text
            else:
                msgs.append({"role": role, "content": text})
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        return msgs

    def snapshot(self):
        w = self.world
        now = datetime.now()
        lines = [f"지금 상태 ({now:%Y-%m-%d %H:%M} {DAYS[now.weekday()]}요일)"]
        try:
            s = w.system_info()
            gib = 2 ** 30
            lines.append(
                f"- {s['os']} · 깨어 있은 지 {span(s['uptime'])} · 메모리 {s['memUsed'] / gib:.1f} / "
                f"{s['memTotal'] / gib:.1f} GB · 디스크 {s['diskUsed'] / gib:.1f} GB 씀"
            )
            sv = w.services()
            lines.append(f"- Docker {'켜짐' if sv['docker'] else '꺼짐'} · 브라우저 터미널 {'켜짐' if sv['term'] else '꺼짐'}")
        except Exception as e:  # 상태 한 줄이 깨져도 대화는 이어 간다.
            lines.append(f"- 시스템 상태를 못 읽음 ({e})")

        lines.append("봇 (이름 / project / 상태)")
        bots = w.bots()
        if bots is None:
            lines.append("- Docker 에 닿지 않아 봇 상태를 모른다")
        elif not bots:
            lines.append("- 올린 봇이 없다")
        for b in bots or []:
            nowt = time.time()
            since = f"일한 지 {span(nowt - b['startedAt'])}" if b["state"] == "running" and b["startedAt"] \
                else (f"쉰 지 {span(nowt - b['finishedAt'])}" if b["finishedAt"] else "")
            extra = []
            if since:
                extra.append(since)
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
        todos = w.todos()
        if not todos:
            lines.append("- 없음")
        for t in todos:
            lines.append(f"- {t['id']} · {t['text']} · {'끝냄' if t['done'] else '남음'}")

        lines.append("오늘 기록")
        evs = w.events()
        if not evs:
            lines.append("- 아직 없음")
        for e in evs:
            lines.append(f"- {datetime.fromtimestamp(e['t']):%H:%M} {e['text']}")
        return "\n".join(lines)

    # 도구 ---------------------------------------------------------------

    def todo_text(self, tid):
        for t in self.world.todos():
            if t["id"] == tid:
                return t["text"]
        return None

    def run_tool(self, name, args):
        """(모델에게 줄 결과, 화면에 띄울 한 줄, 확인 단추 정보, 실패 여부)"""
        w = self.world
        if not isinstance(args, dict):
            return "입력이 객체가 아니다", None, None, True

        if name == "add_todo":
            text = args.get("text")
            if not isinstance(text, str) or not text.strip():
                return "text 가 비었다", None, None, True
            item = w.add_todo(text)
            return json.dumps({"id": item["id"], "text": item["text"]}, ensure_ascii=False), f"할 일 더함 · {item['text']}", None, False

        if name in ("update_todo", "delete_todo"):
            tid = args.get("id")
            if not isinstance(tid, str):
                return "id 가 없다", None, None, True
            if name == "update_todo":
                done = args.get("done")
                if not isinstance(done, bool):
                    return "done 은 true/false 여야 한다", None, None, True
                t = w.change_todo(tid, "set", done)
                if not t:
                    return f"{tid} 라는 할 일이 없다", None, None, True
                return "바꿨다", f"{'할 일 끝' if done else '할 일 되돌림'} · {t['text']}", None, False
            t = w.change_todo(tid, "delete")
            if not t:
                return f"{tid} 라는 할 일이 없다", None, None, True
            return "지웠다", f"할 일 지움 · {t['text']}", None, False

        if name in ("bot_control", "bot_logs"):
            project = args.get("project")
            bot = w.find_bot(project) if isinstance(project, str) else None
            if not bot:
                return f"{project} 라는 봇이 없다", None, None, True
            if name == "bot_logs":
                lines = args.get("lines", 60)
                lines = max(1, min(200, lines if isinstance(lines, int) else 60))
                text = ANSI.sub("", w.bot_logs(bot, lines)).strip()
                # 기록이 길어도 모델에게는 끝부분만. 원인은 대개 마지막 몇십 줄에 있다.
                if len(text) > 8000:
                    text = "...(앞은 잘림)\n" + text[-8000:]
                return text or "(기록이 비었다)", f"{bot['name']} 기록 {lines}줄 읽음", None, False
            action = args.get("action")
            if action not in ("start", "stop", "bake"):
                return "action 은 start, stop, bake 중 하나다", None, None, True
            if action == "start" and bot["guard"]:
                confirm = {"project": bot["project"], "name": bot["name"], "guard": bot["guard"]}
                return ("깨우지 않았다. 대장 화면에 확인 단추를 띄웠다. 대장이 직접 눌러야 깨어난다.",
                        f"{bot['name']} 깨우기 확인 단추 띄움", confirm, False)
            if action == "bake" and not bot["canBake"]:
                return "이 봇은 굽는 스크립트가 없다", None, None, True
            ok = w.bot_act(bot, action)
            word = {"start": "깨움", "stop": "재움", "bake": "굽기 시작"}[action]
            if not ok:
                return f"{word} 실패. 봇 칸의 기록 단추로 이유를 볼 수 있다.", f"{bot['name']} {word} 실패", None, True
            return f"{word} 됐다", f"{bot['name']} {word}", None, False

        return f"{name} 라는 도구는 없다", None, None, True

    # 대화 ---------------------------------------------------------------

    def chat(self, text, emit):
        if anthropic is None:
            emit({"t": "error", "code": "sdk", "d": "비서 부품(anthropic SDK)이 없어. setup.sh 를 다시 돌려 줘."})
            return
        if not self.busy.acquire(blocking=False):
            emit({"t": "error", "code": "busy", "d": "아직 앞 말에 답하는 중이야."})
            return
        try:
            self._chat(text, emit)
        finally:
            self.busy.release()

    def _chat(self, text, emit):
        key = read_key()
        if not key:
            emit({"t": "error", "code": "key", "d": "비서 열쇠가 없어."})
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
        emit({"t": "done"})
