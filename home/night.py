# 하치와레 밤 작업. 대장이 자는 동안(기본 05:00) 오늘 할 일을 파악하고, 혼자 해 둘 수 있는 것 중 가장 작은 하나를
# Windows 쪽 Claude Code 로 미리 해 둔다. 결과는 hachi/... 브랜치로 GitHub 에 올리고, 아침에 대장이 홈 화면에서
# [합치기]·[버리기] 한다.
#
# - 손은 Windows 의 claude.exe 다(WSL interop). 대화 기록이 대장이 평소 쓰는 Windows ~/.claude 에 남아 치이스페나
#   `claude --resume` 으로 그대로 이어 볼 수 있고, 구독 로그인도 거기 있다.
# - 05:00 에 처음 부르는 순간 Claude 의 5시간 창이 열린다. 그 창이 끝날 즈음 아주 작은 요청으로 한 번 더 연다.
#   아침에 일어나든 점심에 일어나든 쓰기 시작하고 몇 시간 안에 한도가 새로 찬다.
# - 밤의 Claude 는 git 자격 증명 없이 돈다(night.gitconfig). 실수로라도 GitHub 에 못 올린다. 올리기·합치기는
#   이 모듈이 자격 증명이 있는 git 으로 hachi/ 브랜치와, 대장이 누른 합치기만 한다.
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
GIT_EXE = "/mnt/c/Program Files/Git/cmd/git.exe"
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

DEFAULTS = {"enabled": False, "at": "05:00", "minutes": 45, "model": "", "triageModel": "haiku"}
WHO = ("hachi", "me", "risky")
# 5시간 창이 닫힌 직후에 다시 연다. 몇 분 여유는 서버 시계와 이쪽 시계가 어긋날 몫이다.
WAKE_AFTER = 5 * 3600 + 180
# 05:00 에 PC 가 꺼져 있었으면 켜진 뒤라도 이 안에는 돈다. 그보다 늦으면 대장이 깨어 있을 수 있어 건너뛴다.
LATE = 3 * 3600
# 밤의 Claude 에게 막는 것. 자격 증명을 빼 둔 것이 진짜 막이고, 이건 시도조차 안 하게 하는 겉막이다.
# 운영 서버(ssh)·Debian 쪽 봇(wsl, docker)·GitHub(gh) 은 밤에 만질 일이 없다. PowerShell 은 wsl 을 부를 수 있어 뺀다.
DENY = ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git config:*)", "Bash(gh:*)", "Bash(ssh:*)", "Bash(scp:*)",
        "Bash(wsl:*)", "Bash(wsl.exe:*)", "Bash(docker:*)", "PowerShell"]
GUARD_ENV = ("GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE")

TRIAGE = """대장의 오늘 할 일을 보고, 하치와레가 대장이 자는 동안 혼자 해 둘 수 있는지 하나씩 나눈다.
하치와레는 밤에 저장소 하나를 받아 새 브랜치에서 코드·문서를 고치고 커밋까지만 하는 Claude Code 다. 사람에게 묻거나,
서버에 접속하거나, 배포하거나, 화면 앞에서 무엇을 누를 수 없다.

저장소 표 (slug, 부르는 이름들, 설명, night=false 면 밤에 손대지 않음):
{repos}

할 일 (id: 내용):
{todos}

나누는 법
- who "hachi": 저장소 하나 안에서 고치고 커밋하면 끝나는 일(버그 고치기, 기능 만들기, 문서·테스트 쓰기).
- who "me": 대장이 직접 해야 하는 일. 특정 PC 앞에서 해야 함, 로그인·결제·사람 상대, 무엇을 원하는지 아직 정해야 하는
  질문이나 아이디어, 어느 저장소 일인지 모름.
- who "risky": 운영 중인 서비스·서버·토큰·배포·실제 데이터를 건드리는 일.
- repo: 저장소 표의 slug 그대로, 모르면 null. repo 가 null 이거나 night=false 인 저장소면 hachi 가 될 수 없다.
- size: 1 작음(한두 파일, 한 시간 안) / 2 보통 / 3 큼(설계가 필요하거나 여러 날).
- why: 그렇게 나눈 까닭, 명사형으로 끝나는 짧은 한 줄(예: "데스크톱 앞 관리자 창 필요", "폰 화면 표시 버그").
- plan: who 가 hachi 일 때만, 밤에 할 첫 걸음 한 줄. 아니면 "".

JSON 배열만 답한다. 다른 말은 쓰지 않는다.
[{{"id": "...", "who": "hachi|me|risky", "repo": "owner/name 또는 null", "size": 1, "why": "...", "plan": "..."}}]"""

TASK = """너는 하치와레다. 대장(이 저장소 주인)이 자는 동안 오늘 할 일 하나를 미리 해 둔다. 아침에 대장이 결과를 보고 합칠지 정한다.

할 일: {text}
저장소: {slug} (지금 폴더). 브랜치 {branch} 에서 일한다. 기준 브랜치는 {base}.
밤에 할 첫 걸음(하치와레가 잡아 둔 것): {plan}

규칙
- 이 폴더 안에서만 일한다. 다른 폴더·다른 저장소·시스템 설정은 건드리지 않고, 프로그램을 시스템에 깔지 않는다.
- 푸시하지 않는다(git 자격 증명이 없어 어차피 안 된다). 브랜치는 끝난 뒤 하치와레가 올린다.
  배포, 서버 접속, 봇이나 서비스 실행, 운영 토큰·실제 데이터 사용은 하지 않는다.
- 저장소의 CLAUDE.md·AGENTS.md·README 에 적힌 규칙을 먼저 읽고 따른다.
- 이모지는 코드·주석·커밋·문서 어디에도 쓰지 않는다. 주석은 코드가 말하지 않는 이유만 쓴다.
- 테스트나 검사가 있으면 돌린다. 도구가 없어 못 돌리면 깔지 말고 마지막 보고에 적는다.
- 할 일이 생각보다 크면 오늘 밤 끝낼 수 있는 첫 조각만 하고, 남은 것을 보고에 적는다.
- 무엇을 원하는지 애매해서 추측이 커지면 코드를 고치지 말고, 대장에게 물어볼 것만 정리해서 끝낸다.
- 마친 일은 이 브랜치에 커밋한다. 커밋 제목은 명사형 라벨(예: "폰 화면 작업 중 표시 수정"), 접두사(feat: 등)와
  마침표 없이. 본문은 평서형(~한다)으로 왜 그렇게 했는지. 맨 끝 줄은 "Co-Authored-By: Claude <noreply@anthropic.com>"
  하나만 두고 다른 서명 줄은 넣지 않는다.

마지막 답은 대장에게 하는 아침 보고다. 한국어 반말, 다섯 줄 안팎, 줄마다 "- " 로 시작하고 마크다운 제목·표·굵게는 쓰지 않는다.
한 일, 확인한 것(테스트), 못 한 것이나 대장에게 물어볼 것을 적는다."""


def linux_path(win):
    return subprocess.run(["wslpath", "-u", win], capture_output=True, text=True).stdout.strip()


class Night:
    def __init__(self, state_dir, log_event, todos):
        self.dir = Path(state_dir) / "night"
        self.log_event = log_event
        self.todos = todos
        self.files = threading.RLock()
        self.job = threading.Lock()
        self.triaging = threading.Lock()
        self.triage_due = 0.0
        self._win = None
        self.live = None

    # 파일 ------------------------------------------------------------------

    def _read(self, name, default):
        try:
            return json.loads((self.dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _write(self, name, obj):
        with self.files:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / (name + ".tmp")
            tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.dir / name)

    def settings(self):
        return {**DEFAULTS, **self._read("settings.json", {})}

    def set_settings(self, data):
        s = self.settings()
        if "enabled" in data:
            s["enabled"] = bool(data["enabled"])
        if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(data.get("at", ""))):
            s["at"] = data["at"]
        if isinstance(data.get("minutes"), int) and 5 <= data["minutes"] <= 180:
            s["minutes"] = data["minutes"]
        for k in ("model", "triageModel"):
            if isinstance(data.get(k), str) and re.fullmatch(r"[\w.\-\[\]]{0,60}", data[k]):
                s[k] = data[k]
        self._write("settings.json", s)
        return s

    def runs(self):
        return self._read("runs.json", [])

    def _save_run(self, run):
        with self.files:
            runs = [r for r in self._read("runs.json", []) if r["id"] != run["id"]] + [dict(run)]
            self._write("runs.json", runs[-30:])

    def catalog(self):
        p = Path(os.environ.get("CHII_NIGHT_REPOS") or HERE / "repos.json")
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("repos") or []
        except (OSError, ValueError):
            return []

    def repo(self, slug):
        for r in self.catalog():
            if r["slug"].lower() == str(slug or "").lower():
                return r
        return None

    # Windows 쪽 -----------------------------------------------------------

    def win(self):
        """claude.exe 와 밤 작업 폴더. 노트북·데스크톱의 사용자 폴더 이름이 달라 Windows 에 물어야 안다."""
        if self._win:
            return self._win
        out = subprocess.run(
            [POWERSHELL, "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $env:USERPROFILE; "
             "(Get-Command claude -ErrorAction SilentlyContinue).Source"],
            capture_output=True, timeout=60).stdout.decode("utf-8", "replace").splitlines()
        home = out[0].strip() if out else ""
        claude = out[1].strip() if len(out) > 1 else ""
        if not claude and home:
            claude = home + r"\.local\bin\claude.exe"
        if not home:
            raise RuntimeError("Windows 사용자 폴더를 못 찾았어")
        claude_l = linux_path(claude) if claude else ""
        if not claude_l or not Path(claude_l).exists():
            raise RuntimeError("Windows 쪽 claude 가 없어. Claude Code 를 깔고 로그인해 줘")
        root = os.environ.get("CHII_NIGHT_ROOT") or home + r"\chiios-night"
        self._win = {"home": home, "claude": claude_l, "root": root, "rootL": linux_path(root)}
        return self._win

    def _git(self, windir, *args, timeout=300):
        try:
            p = subprocess.run([GIT_EXE, "-C", windir, *args], capture_output=True, timeout=timeout,
                               env=self._env())
            return p.returncode, (p.stdout + p.stderr).decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)

    def _env(self, guard=None):
        # 새벽에 자격 증명 창이 떠서 멈춰 있지 않게, 묻는 길은 다 막는다.
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        names = ["GIT_TERMINAL_PROMPT", "GCM_INTERACTIVE"]
        if guard:
            env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=guard)
            names += ["GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL"]
        env["WSLENV"] = ":".join([x for x in os.environ.get("WSLENV", "").split(":") if x and x.split("/")[0] not in GUARD_ENV] + names)
        return env

    def _guard_config(self):
        """밤의 Claude 가 쓸 git 설정. 원래 설정(줄 끝 처리·이름)은 그대로 읽고 자격 증명만 비운다.
        빈 helper 는 그 앞까지 쌓인 목록을 지운다. 환경 변수로는 빈 값을 Windows 에 못 넘겨서 파일로 둔다."""
        w = self.win()
        home = w["home"].replace("\\", "/")
        text = ("[include]\n\tpath = C:/Program Files/Git/etc/gitconfig\n"
                f"\tpath = {home}/.gitconfig\n"
                "[credential]\n\thelper =\n"
                "[credential \"https://github.com\"]\n\thelper =\n"
                "[credential \"https://gist.github.com\"]\n\thelper =\n"
                "[core]\n\tsshCommand = false\n")
        Path(w["rootL"]).mkdir(parents=True, exist_ok=True)
        (Path(w["rootL"]) / "night.gitconfig").write_text(text, encoding="utf-8")
        return w["root"] + r"\night.gitconfig"

    def _claude(self, args, cwd_l, prompt, timeout, guard=None, on_event=None, log_path=None):
        """claude.exe 를 돌리고 stream-json/json 을 읽는다. 시간이 넘으면 멈춘다(interop 쪽을 끝내면 Windows 쪽도 끝난다)."""
        w = self.win()
        p = subprocess.Popen([w["claude"], *args], cwd=cwd_l, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=self._env(guard=guard))
        killed = []

        def kill():
            killed.append(1)
            p.terminate()

        timer = threading.Timer(timeout, kill)
        timer.start()
        last = None
        out = []
        logf = open(log_path, "ab") if log_path else None
        try:
            p.stdin.write(prompt.encode("utf-8"))
            p.stdin.close()
            for raw in p.stdout:
                if logf:
                    logf.write(raw)
                line = raw.decode("utf-8", "replace").strip()
                out.append(line)
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                # json 출력은 판에 따라 결과 하나가 아니라 사건 전체의 배열로 온다(2.1.328 실측). 둘 다 받는다.
                for x in ev if isinstance(ev, list) else [ev]:
                    if isinstance(x, dict):
                        if x.get("type") == "result":
                            last = x
                        if on_event:
                            on_event(x)
            p.wait()
        finally:
            timer.cancel()
            if logf:
                logf.close()
        if last is None:
            try:
                whole = json.loads("\n".join(out))
                last = next((x for x in (whole if isinstance(whole, list) else [whole])
                             if isinstance(x, dict) and x.get("type") == "result"), None)
            except ValueError:
                pass
        return p.returncode, last, bool(killed), "\n".join(out[-20:])

    # 파악 ------------------------------------------------------------------

    def who(self, e):
        return e.get("override") or e.get("who") or "me"

    def touch(self):
        """할 일이 바뀌었다. 몰아서 한 번만 파악하게 잠깐 기다렸다가 한다."""
        if self.settings()["enabled"]:
            self.triage_due = time.time() + 90

    def triage(self, force=False):
        if not self.triaging.acquire(blocking=False):
            return False
        try:
            todos = [t for t in self.todos() if not t.get("done")]
            cur = self._read("triage.json", {})
            ids = {t["id"] for t in todos}
            cur = {k: v for k, v in cur.items() if k in ids}
            need = [t for t in todos if force or cur.get(t["id"], {}).get("text") != t["text"]]
            if not need:
                self._write("triage.json", cur)
                return True
            cat = self.catalog()
            repos = "\n".join(f"- {r['slug']} | {', '.join(r.get('names') or [])} | {r.get('about', '')}"
                              f"{' | night=false' if r.get('night') is False else ''}" for r in cat)
            prompt = TRIAGE.format(repos=repos or "(없음)", todos="\n".join(f"- {t['id']}: {t['text']}" for t in need))
            w = self.win()
            Path(w["rootL"]).mkdir(parents=True, exist_ok=True)
            code, res, _, tail = self._claude(
                ["-p", "--model", self.settings()["triageModel"] or "haiku", "--output-format", "json",
                 "--no-session-persistence", "--permission-mode", "dontAsk"],
                w["rootL"], prompt, timeout=300)
            text = (res or {}).get("result") or ""
            try:
                items = json.loads(text[text.index("["):text.rindex("]") + 1])
            except ValueError:
                self.log_event("night", "하치와레 할 일 파악 실패 · 답을 못 읽음")
                return False
            slugs = {r["slug"].lower(): r for r in cat}
            now = time.time()
            for it in items if isinstance(items, list) else []:
                t = next((x for x in need if x["id"] == str(it.get("id"))), None)
                if not t:
                    continue
                r = slugs.get(str(it.get("repo") or "").lower())
                who = it.get("who") if it.get("who") in WHO else "me"
                why = str(it.get("why") or "")[:60]
                if who == "hachi" and (not r or r.get("night") is False):
                    who, why = "me", "어느 저장소 일인지 모름" if not r else "밤에 손대지 않는 저장소"
                try:
                    size = min(3, max(1, int(it.get("size") or 2)))
                except (TypeError, ValueError):
                    size = 2
                old = cur.get(t["id"]) or {}
                cur[t["id"]] = {
                    "text": t["text"], "who": who, "repo": r["slug"] if r else None, "size": size, "why": why,
                    "plan": str(it.get("plan") or "")[:200] if who == "hachi" else "", "t": now,
                    # 대장이 고쳐 둔 것은 내용이 그대로인 동안 지킨다.
                    **({"override": old["override"]} if old.get("override") and old.get("text") == t["text"] else {}),
                }
            self._write("triage.json", cur)
            return True
        except Exception as e:  # noqa: BLE001 - 밤에 혼자 도는 일이라 어떤 실패든 기록만 남기고 넘어간다
            self.log_event("night", f"하치와레 할 일 파악 실패 · {str(e)[:80]}")
            return False
        finally:
            self.triaging.release()

    def set_who(self, tid, who):
        cur = self._read("triage.json", {})
        if tid not in cur:
            return None
        if who in WHO and who != cur[tid].get("who"):
            cur[tid]["override"] = who
        else:
            cur[tid].pop("override", None)
        if self.who(cur[tid]) == "hachi" and not cur[tid].get("repo"):
            return None
        self._write("triage.json", cur)
        return cur[tid]

    # 고르기·하기 -----------------------------------------------------------

    def pick(self, todo_id=None):
        tri = self._read("triage.json", {})
        tried = {(r["todo"]["id"], r["todo"]["text"]) for r in self.runs()
                 if r.get("todo") and r.get("status") in ("done", "nothing", "failed")}
        cands = []
        for t in self.todos():
            e = tri.get(t["id"])
            if t.get("done") or not e or e.get("text") != t["text"] or not e.get("repo"):
                continue
            if todo_id:
                if t["id"] == todo_id:
                    return t, e
                continue
            if self.who(e) == "hachi" and (t["id"], t["text"]) not in tried:
                cands.append((e.get("size", 2), t.get("createdAt") or 0, t, e))
        cands.sort(key=lambda c: (c[0], c[1]))
        return (cands[0][2], cands[0][3]) if cands else None

    def prepare(self, slug, branch):
        w = self.win()
        info = self.repo(slug) or {}
        url = info.get("url") or f"https://github.com/{slug}.git"
        windir = w["root"] + "\\" + slug.replace("/", "-")
        lin = Path(linux_path(windir))
        if not (lin / ".git").exists():
            Path(w["rootL"]).mkdir(parents=True, exist_ok=True)
            code, out = self._git(w["root"], "clone", url, windir, timeout=1200)
            if code:
                raise RuntimeError(f"저장소를 못 받았어: {out.strip()[-160:]}")
        self._git(windir, "remote", "set-url", "origin", url)
        # 밤의 Claude 가 올리려 해도 갈 곳이 없게. 하치와레는 주소를 직접 적어 올린다.
        self._git(windir, "remote", "set-url", "--push", "origin", "no-push-from-night-work")
        code, out = self._git(windir, "fetch", "--prune", "origin", timeout=600)
        if code:
            raise RuntimeError(f"저장소를 못 받았어: {out.strip()[-160:]}")
        self._git(windir, "remote", "set-head", "origin", "--auto")
        code, head = self._git(windir, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        base = head.strip().split("/", 1)[1] if code == 0 and "/" in head else "main"
        self._git(windir, "reset", "--hard")
        self._git(windir, "clean", "-fd")
        code, out = self._git(windir, "checkout", "-B", branch, f"origin/{base}")
        if code:
            raise RuntimeError(f"브랜치를 못 만들었어: {out.strip()[-160:]}")
        guard = self._guard_config()
        env = self._env(guard=guard)
        name = subprocess.run([GIT_EXE, "-C", windir, "config", "user.name"], capture_output=True, env=env).stdout.strip()
        if not name:
            # 데스크톱은 git 으로 받기만 해서 이름이 없을 수 있다. 없으면 커밋이 실패하니 GitHub 계정 이름으로 둔다.
            owner = slug.split("/")[0]
            self._git(windir, "config", "user.name", owner)
            self._git(windir, "config", "user.email", f"{owner}@users.noreply.github.com")
        return windir, base, url, guard

    def run_task(self, t, e, reason):
        slug = e["repo"]
        now = datetime.now()
        branch = f"hachi/{now:%m%d}-{t['id']}"
        run = {"id": now.strftime("%Y%m%d-%H%M%S"), "t": time.time(), "todo": {"id": t["id"], "text": t["text"]},
               "repo": slug, "branch": branch, "status": "running", "reason": reason, "steps": 0}
        self.live = run
        self._save_run(run)
        self.log_event("night", f"하치와레 밤 작업 시작 · {t['text']}")
        try:
            windir, base, url, guard = self.prepare(slug, branch)
            run.update(base=base, cwd=windir)
            self._save_run(run)
            s = self.settings()
            args = ["-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions"]
            if s.get("model"):
                args += ["--model", s["model"]]
            args += ["--disallowedTools", *DENY]

            def on_event(ev):
                if ev.get("type") == "system" and ev.get("session_id"):
                    run["sessionId"] = ev["session_id"]
                if ev.get("type") == "assistant":
                    for c in (ev.get("message") or {}).get("content") or []:
                        if c.get("type") == "tool_use":
                            run["steps"] += 1

            log = self.dir / "logs" / f"{run['id']}.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            code, res, timed_out, tail = self._claude(
                args, linux_path(windir), TASK.format(text=t["text"], slug=slug, branch=branch, base=base,
                                                      plan=e.get("plan") or "(없음, 직접 정한다)"),
                timeout=s["minutes"] * 60, guard=guard, on_event=on_event, log_path=log)
            res = res or {}
            run["summary"] = (res.get("result") or "").strip()[:4000]
            run["sessionId"] = res.get("session_id") or run.get("sessionId")
            if timed_out:
                run["error"] = f"{s['minutes']}분이 넘어 멈췄어"
            elif res.get("is_error") or code not in (0, None):
                run["error"] = (res.get("result") or tail or f"claude 가 {code} 로 끝남").strip()[-300:]
            code, log_ = self._git(windir, "log", "--format=%h%x09%s", f"origin/{base}..HEAD")
            commits = [dict(zip(("sha", "subject"), ln.split("\t", 1))) for ln in log_.splitlines() if "\t" in ln]
            _, st = self._git(windir, "status", "--porcelain")
            run["commits"] = commits
            run["dirty"] = len([ln for ln in st.splitlines() if ln.strip()])
            if commits:
                code, out = self._git(windir, "push", "--force", url, f"HEAD:refs/heads/{branch}", timeout=600)
                if code:
                    run["error"] = f"브랜치를 못 올렸어: {out.strip()[-160:]}"
                    run["status"] = "failed"
                else:
                    run["status"] = "done"
                    run["compare"] = f"https://github.com/{slug}/compare/{quote(base)}...{quote(branch)}"
            else:
                run["status"] = "failed" if run.get("error") else "nothing"
        except Exception as ex:  # noqa: BLE001
            run["status"] = "failed"
            run["error"] = str(ex)[:300]
        finally:
            run["end"] = time.time()
            self.live = None
            self._save_run(run)
            word = {"done": f"커밋 {len(run.get('commits') or [])}개 올림", "nothing": "고친 것 없음",
                    "failed": "못 끝냄"}.get(run["status"], run["status"])
            self.log_event("night", f"하치와레 밤 작업 · {t['text']} · {word}")
        return run

    def night(self, todo_id=None, reason="night"):
        if not self.job.acquire(blocking=False):
            return False
        try:
            t0 = time.time()
            self.triage()
            if reason == "night":
                st = self._read("state.json", {})
                st["wakeAt"] = t0 + WAKE_AFTER
                self._write("state.json", st)
            got = self.pick(todo_id)
            if not got:
                run = {"id": datetime.now().strftime("%Y%m%d-%H%M%S"), "t": t0, "end": time.time(), "status": "none",
                       "reason": reason, "todo": None}
                if todo_id:
                    run["error"] = "그 할 일은 어느 저장소 일인지 몰라서 못 했어"
                self._save_run(run)
                self.log_event("night", "하치와레 밤 작업 · " + (run.get("error") or "혼자 해 둘 만한 할 일이 없었어"))
                # 할 일이 그대로면 파악도 Claude 를 안 불러서, 일이 없는 밤엔 5시간 창이 이 시각에 안 열린다.
                if reason == "night":
                    self.wake()
                return True
            self.run_task(*got, reason)
            return True
        finally:
            self.job.release()

    def start(self, todo_id=None):
        if self.job.locked():
            return False
        threading.Thread(target=self.night, args=(todo_id, "manual"), daemon=True).start()
        return True

    def wake(self):
        """5시간 창을 다시 연다. 할 일은 없고 아주 짧은 답 하나만 받는다."""
        try:
            w = self.win()
            self._claude(["-p", "--model", "haiku", "--output-format", "json", "--no-session-persistence",
                          "--permission-mode", "dontAsk"], w["rootL"], "한 단어로만 답해: 좋은 아침", timeout=180)
            st = self._read("state.json", {})
            st["wokeAt"] = time.time()
            self._write("state.json", st)
        except Exception:  # noqa: BLE001
            pass

    # 아침에 대장이 누르는 것 ---------------------------------------------------

    def resolve(self, rid, act):
        run = next((r for r in self.runs() if r["id"] == rid), None)
        if not run:
            return None, "그 밤 작업을 못 찾았어"
        if run.get("resolved") or run["status"] == "running":
            return None, "이미 끝난 일이야"
        if act in ("merge", "drop") and run["status"] != "done":
            return None, "올린 브랜치가 없어"
        if act == "merge":
            err = self._merge(run)
            if err:
                return None, err
        elif act == "drop":
            url = (self.repo(run["repo"]) or {}).get("url") or f"https://github.com/{run['repo']}.git"
            self._git(run["cwd"], "push", url, "--delete", run["branch"], timeout=300)
        run["resolved"] = {"merge": "merged", "drop": "dropped"}.get(act, "seen")
        run["resolvedAt"] = time.time()
        self._save_run(run)
        if act in ("merge", "drop"):
            self.log_event("night", f"하치와레 밤 작업 {'합침' if act == 'merge' else '버림'} · {run['todo']['text']}")
        return run, None

    def _merge(self, run):
        """기준 브랜치 위로 줄 세워(rebase) 앞으로 감기만 한다. 그 사이 대장이 올린 커밋과 겹치면 손대지 않고 알린다."""
        if not self.job.acquire(blocking=False):
            return "하치와레가 지금 다른 일을 하는 중이야. 끝나고 다시 눌러 줘"
        try:
            d, base, branch = run["cwd"], run["base"], run["branch"]
            url = (self.repo(run["repo"]) or {}).get("url") or f"https://github.com/{run['repo']}.git"
            code, out = self._git(d, "fetch", "--prune", "origin", timeout=600)
            if code:
                return f"저장소를 못 받았어: {out.strip()[-120:]}"
            self._git(d, "reset", "--hard")
            self._git(d, "checkout", branch)
            code, out = self._git(d, "rebase", f"origin/{base}")
            if code:
                self._git(d, "rebase", "--abort")
                return "그 사이 바뀐 것과 겹쳐서 못 합쳤어. GitHub 에서 직접 봐 줘"
            code, out = self._git(d, "push", url, f"HEAD:refs/heads/{base}", timeout=600)
            if code:
                return f"못 올렸어: {out.strip()[-160:]}"
            self._git(d, "push", url, "--delete", branch, timeout=300)
            return None
        finally:
            self.job.release()

    # 화면에 줄 것 ------------------------------------------------------------

    def view(self):
        s = self.settings()
        tri = self._read("triage.json", {})
        runs = self.runs()
        last = self.live or (runs[-1] if runs else None)
        show = last if last and (last["status"] == "running" or not last.get("resolved")) else None
        keys = ("id", "t", "end", "todo", "repo", "branch", "base", "status", "summary", "commits", "dirty",
                "compare", "sessionId", "cwd", "error", "steps", "reason")
        return {
            "enabled": s["enabled"], "at": s["at"], "busy": self.job.locked(), "triaging": self.triaging.locked(),
            "triage": {k: {"who": self.who(v), "auto": v.get("who"), "repo": v.get("repo"), "size": v.get("size"),
                           "why": v.get("why"), "plan": v.get("plan"), "text": v.get("text")} for k, v in tri.items()},
            "run": {k: show.get(k) for k in keys} if show else None,
        }

    # 시계 ------------------------------------------------------------------

    def watch(self):
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(30)

    def tick(self):
        s = self.settings()
        st = self._read("state.json", {})
        if st.get("wakeAt") and time.time() >= st["wakeAt"]:
            st["wakeAt"] = None
            self._write("state.json", st)
            threading.Thread(target=self.wake, daemon=True).start()
        if not s["enabled"]:
            return
        now = datetime.now()
        hh, mm = (int(x) for x in s["at"].split(":"))
        start = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        today = now.strftime("%Y-%m-%d")
        if st.get("lastNight") != today and start <= now < start + timedelta(seconds=LATE):
            st["lastNight"] = today
            self._write("state.json", st)
            threading.Thread(target=self.night, daemon=True).start()
        elif self.triage_due and time.time() >= self.triage_due and not self.job.locked():
            self.triage_due = 0.0
            threading.Thread(target=self.triage, daemon=True).start()
