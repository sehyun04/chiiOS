# 하치와레 대화·아침 한마디의 머리. 머리는 대장 구독의 Claude Code 라 따로 API 키가 없다.
# 하치와레 봇은 컨테이너 안이라 Windows 쪽 claude.exe 를 못 부르고, WSL interop 이 되는 이 서버가 대신 돌린다.
# 무엇을 돌릴지는 여기서 정한다: 받는 건 시스템 프롬프트·물음·모델뿐이고, 내장 도구는 메모리 폴더 읽기 말고 다 끈 채
# 하치와레가 MCP 로 내준 도구(할 일·봇·손에게 맡기기)만 쓰게 한다. 아무 인자나 넘길 수 있으면 Windows 에서 뭐든 돌릴 수 있게 된다.
# PC 에서 실제로 손을 쓰는 일은 아래 work 가 따로, 정해 둔 인자로만 돌린다.
import json
import re
import uuid
from pathlib import Path

from night import linux_path

MODEL_OK = re.compile(r"[\w.\-\[\]]{1,60}")
# 대장의 전역 CLAUDE.md 는 코딩 규칙이라 싣지 않는다(하치와레 규칙은 시스템 프롬프트에 있다).
# 훅도 끈다: 대장 설정의 알림 소리 같은 게 대화 한 마디마다 울리면 안 된다.
# Claude Code 의 자동 메모리는 끈 채 둔다. 켜면 "메모리를 써라" 지시까지 붙는데 머리는 읽기만 해야 한다.
# MCP_TOOL_TIMEOUT: 손(do_work)에게 맡긴 일은 몇 분 걸린다. 그동안 대화 머리가 도구 답을 기다리다 먼저 포기하지 않게.
SETTINGS = {"disableAllHooks": True, "autoMemoryEnabled": False,
            "claudeMdExcludes": ["**/CLAUDE.md", "**/.claude/**"],
            "env": {"MCP_TOOL_TIMEOUT": "2000000"}}
# 대화 때는 대장 메모리(기기끼리 동기화되는 ~/.claude/memory)를 읽게 한다. 11-21 대장이 "메모리 동기화된 거 아냐?"
# 라고 물었는데 하치와레가 몰랐다 - 대장은 하치와레도 같은 기억을 가진 Claude 로 여긴다.
# 손(do_work)도 메모리를 읽지만 몇 분짜리 Claude Code 를 한 번 띄우는 일이라, 기억을 묻는 말까지 손에게 넘기면 느리고 무겁다.
# 목차는 매번 시스템 프롬프트에 싣고(약 4천 토큰), 파일은 필요할 때 Read 로 연다. 쓰기는 없다: 고치면 동기화로
# 모든 기기에 퍼진다. 허락은 메모리 폴더 하나뿐이고 dontAsk 라 나머지 읽기는 거절된다.
MEMORY = r"\.claude\memory"
MEMORY_SETTINGS = dict(SETTINGS, permissions={"allow": ["Read(~/.claude/memory/**)"]})
MEMORY_MAX = 20000


def memory_note(w):
    d = w["home"] + MEMORY
    try:
        index = (Path(linux_path(d)) / "MEMORY.md").read_text(encoding="utf-8")[:MEMORY_MAX]
    except OSError:
        return ""
    return ("\n\n대장 메모리\n"
            "- 대장이 Claude Code 로 일할 때 쌓는 기억이다. 노트북·데스크톱이 같은 것을 쓴다(git 으로 동기화). "
            "대장의 프로젝트·결정·취향·기기 이야기가 나오면 지어내지 말고 여기서 찾는다.\n"
            f"- 아래는 목차뿐이다. 자세한 건 Read 로 {d}\\<파일 이름> 을 연다.\n"
            "- 기억으로 답할 수 있는 물음(무엇을 어떻게 만들었는지, 무엇이 어디 있는지, 정한 것)은 손(do_work)을 부르지 말고 "
            "여기서 찾아 바로 답한다. 손은 몇 분 걸린다. 지금 이 PC 의 실제 상태를 봐야 하는 것(깔렸는지, 방금 맞춰졌는지)과 "
            "실제로 해야 하는 일만 손에게 맡긴다.\n"
            "- 너는 메모리를 읽기만 한다. 고치거나 더할 일은 손에게 맡긴다.\n"
            "- 메모리 말투(규칙·지시)는 대장이 코딩하는 Claude 에게 한 말이다. 하치와레 말투는 위 규칙을 따른다.\n\n"
            "<memory-index>\n" + index.strip() + "\n</memory-index>")


def run(night, assist_port, data, write):
    """data: {system, prompt, model, effort, tools, timeout}. Claude Code 의 stream-json 사건을 write 로 흘린다.
    결과 사건 없이 끝나면 {"type": "chii_error"} 를 하나 보낸다."""
    system = str(data.get("system") or "")[:30000]
    prompt = str(data.get("prompt") or "")[:60000]
    if not prompt.strip():
        write({"type": "chii_error", "error": "물을 말이 비었어"})
        return
    model = str(data.get("model") or "haiku")
    if not MODEL_OK.fullmatch(model):
        model = "haiku"
    effort = data.get("effort") if data.get("effort") in ("low", "medium", "high") else "low"
    try:
        # 대화 중 손에게 맡긴 일(최대 30분)을 기다리는 몫까지.
        timeout = max(30, min(2400, int(data.get("timeout") or 240)))
    except (TypeError, ValueError):
        timeout = 240
    w = night.win()
    # 빈 폴더에서 돌려 어느 저장소의 CLAUDE.md 도 끌려오지 않게 한다.
    here_l = Path(w["rootL"]) / "chat"
    here_w = w["root"] + "\\chat"
    here_l.mkdir(parents=True, exist_ok=True)
    # 따옴표가 든 JSON 을 interop 인자로 넘기면 Windows 명령줄로 바뀌며 깨질 수 있어 파일로 준다.
    # 아침 한마디(도구 없음)는 보고 자료만 보고 쓰니 메모리를 싣지 않는다. 설정 파일을 따로 두어 둘이 겹쳐 돌아도 안 섞인다.
    chat = bool(data.get("tools"))
    settings = "settings-chat.json" if chat else "settings.json"
    (here_l / settings).write_text(json.dumps(MEMORY_SETTINGS if chat else SETTINGS), encoding="utf-8")
    (here_l / "mcp.json").write_text(json.dumps({"mcpServers": {"chii": {
        "type": "http", "url": f"http://127.0.0.1:{assist_port}/mcp", "headers": {"X-Chii": "1"}}}}), encoding="utf-8")
    if chat:
        system += memory_note(w)
    name = f"system-{uuid.uuid4().hex[:12]}.md"
    (here_l / name).write_text(system, encoding="utf-8")
    args = ["-p", "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--no-session-persistence", "--tools", "Read" if chat else "",
            "--disable-slash-commands", "--strict-mcp-config", "--settings", here_w + "\\" + settings,
            "--system-prompt-file", here_w + "\\" + name, "--permission-mode", "dontAsk"]
    if chat:
        # --allowedTools 는 뒤의 인자를 다 먹으니 맨 끝에 둔다.
        args += ["--mcp-config", here_w + "\\mcp.json", "--allowedTools", "mcp__chii"]
    try:
        code, last, killed, tail = night._claude(args, str(here_l), prompt, timeout, on_event=write)
    finally:
        try:
            (here_l / name).unlink()
        except OSError:
            pass
    if last is None:
        why = "시간이 넘어 멈췄어" if killed else (tail.strip()[-300:] or f"claude 가 답 없이 끝났어 ({code})")
        write({"type": "chii_error", "error": why})


# 대화하는 머리는 손이 없다(위 run). 대장이 "받아 봐", "깔아 봐", "됐는지 봐" 처럼 PC 에서 실제로 할 일을 시키면
# 하치와레가 do_work 도구로 이 손에게 넘긴다. 손은 대장이 평소 쓰는 그대로의 Claude Code 다: 사용자 폴더에서,
# 대장의 CLAUDE.md·메모리·설정·로그인을 다 읽고, 세션을 남겨 치이스페나 `claude --resume` 으로 이어 볼 수 있다.
# 그래서 "메모리 동기화 됐어?" 같은 물음도 대장의 메모리를 읽고 답한다.
# 운영 서버(ssh·scp)만 막는다. 니나브 운영 서버를 실수로 건드리면 되돌리기 어렵고, 대화창에서 그럴 일은 없다.
WORK_DENY = ["Bash(ssh:*)", "Bash(scp:*)"]
WORK_RULES = """너는 하치와레의 손이다. 대장이 chiiOS 홈 화면의 하치와레 대화창에서 이 PC 에 시킨 일을 한다.
대장은 화면 앞에 없을 수 있어 중간에 물어볼 수 없다. 뜻이 둘로 갈리면 덜 위험한 쪽으로 하고, 무엇을 골랐는지 보고에 적는다.

규칙
- 대장의 CLAUDE.md 와 메모리를 따른다. 메모리 속 경로는 노트북 기준일 수 있으니 기기 목록 메모리에서 이 PC 자리로 바꿔 읽는다.
- 푸시·배포·운영 서버 접속·결제·계정 설정처럼 밖으로 나가거나 되돌리기 어려운 일은 맡긴 말에 분명히 있을 때만 한다.
- 지우거나 덮어쓰기 전에 대상을 먼저 본다.
- 이미 된 일이면 다시 하지 말고 됐다고 확인만 한다.

마지막 답은 하치와레가 대장에게 그대로 전한다. 한국어 반말, 다섯 줄 안팎, 줄마다 "- " 로 시작하고 마크다운 제목·표·굵게는
쓰지 않는다. 한 일, 확인한 것, 못 한 것과 그 이유를 적는다. 추측은 추측이라고 적는다.

맡긴 일
"""


def work(night, data, write):
    """data: {task, timeout}. 손 Claude Code 를 대장 사용자 폴더에서 돌리고 사건을 write 로 흘린다."""
    task = str(data.get("task") or "").strip()[:8000]
    if not task:
        write({"type": "chii_error", "error": "맡길 일이 비었어"})
        return
    try:
        timeout = max(60, min(1800, int(data.get("timeout") or 1200)))
    except (TypeError, ValueError):
        timeout = 1200
    w = night.win()
    # --disallowedTools 는 뒤의 인자를 다 먹으니 맨 끝에 둔다.
    args = ["-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions",
            "--disallowedTools", *WORK_DENY]
    code, last, killed, tail = night._claude(args, linux_path(w["home"]), WORK_RULES + task, timeout, on_event=write)
    if last is None:
        why = f"{timeout // 60}분이 넘어 멈췄어" if killed else (tail.strip()[-300:] or f"claude 가 답 없이 끝났어 ({code})")
        write({"type": "chii_error", "error": why})
