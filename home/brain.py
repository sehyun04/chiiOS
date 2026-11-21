# 하치와레 대화·아침 한마디의 머리. 머리는 대장 구독의 Claude Code 라 따로 API 키가 없다.
# 하치와레 봇은 컨테이너 안이라 Windows 쪽 claude.exe 를 못 부르고, WSL interop 이 되는 이 서버가 대신 돌린다.
# 무엇을 돌릴지는 여기서 정한다: 받는 건 시스템 프롬프트·물음·모델뿐이고, 내장 도구(셸·파일)는 다 끈 채
# 하치와레가 MCP 로 내준 도구(할 일·봇)만 쓰게 한다. 아무 인자나 넘길 수 있으면 Windows 에서 뭐든 돌릴 수 있게 된다.
import json
import re
import uuid
from pathlib import Path

MODEL_OK = re.compile(r"[\w.\-\[\]]{1,60}")
# 대장의 전역 CLAUDE.md·자동 메모리를 매번 싣지 않는다(실측 6.5천 -> 0.8천 토큰). 하치와레 규칙은 시스템 프롬프트에 있다.
# 훅도 끈다: 대장 설정의 알림 소리 같은 게 대화 한 마디마다 울리면 안 된다.
SETTINGS = {"disableAllHooks": True, "autoMemoryEnabled": False,
            "claudeMdExcludes": ["**/CLAUDE.md", "**/.claude/**"]}


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
        timeout = max(30, min(600, int(data.get("timeout") or 240)))
    except (TypeError, ValueError):
        timeout = 240
    w = night.win()
    # 빈 폴더에서 돌려 어느 저장소의 CLAUDE.md 도 끌려오지 않게 한다.
    here_l = Path(w["rootL"]) / "chat"
    here_w = w["root"] + "\\chat"
    here_l.mkdir(parents=True, exist_ok=True)
    # 따옴표가 든 JSON 을 interop 인자로 넘기면 Windows 명령줄로 바뀌며 깨질 수 있어 파일로 준다.
    (here_l / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    (here_l / "mcp.json").write_text(json.dumps({"mcpServers": {"chii": {
        "type": "http", "url": f"http://127.0.0.1:{assist_port}/mcp", "headers": {"X-Chii": "1"}}}}), encoding="utf-8")
    name = f"system-{uuid.uuid4().hex[:12]}.md"
    (here_l / name).write_text(system, encoding="utf-8")
    args = ["-p", "--model", model, "--effort", effort, "--output-format", "stream-json", "--verbose",
            "--include-partial-messages", "--no-session-persistence", "--tools", "", "--disable-slash-commands",
            "--strict-mcp-config", "--settings", here_w + "\\settings.json",
            "--system-prompt-file", here_w + "\\" + name, "--permission-mode", "dontAsk"]
    if data.get("tools"):
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
