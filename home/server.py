#!/usr/bin/env python3
# chiiOS 홈 화면. 봇·할 일·기록을 보여 주고, 터미널 칸은 ttyd 웹소켓을 이어 받아 직접 그린다.
# 표준 라이브러리만 쓴다. 봇 돌리는 기계에 pip 패키지를 들이면 setup.sh 가 챙길 것이 늘고 업데이트 때 깨질 곳도 는다.
# 비서는 따로 도는 봇(bots/assistant)이라 SDK 도 그 이미지 안에만 있다. 여기서는 [비서] 탭의 말을 넘겨주기만 한다.
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
BOTS_DIR = Path(os.environ.get("CHII_BOTS_DIR", str(HERE.parent / "bots")))
STATE_DIR = Path(os.environ.get("CHII_STATE_DIR", str(Path.home() / ".local/share/chiios")))
HOST = os.environ.get("CHII_HOME_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHII_HOME_PORT", "7682"))
TERM_PORT = int(os.environ.get("CHII_TERM_PORT", "7681"))
ASSIST_PORT = int(os.environ.get("CHII_ASSIST_PORT", "7683"))
ASSIST_PROJECT = "assistant"

TODOS = STATE_DIR / "todos.json"
EVENTS = STATE_DIR / "events.jsonl"
lock = threading.Lock()
baking = {}

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".png": "image/png",
    ".ttf": "font/ttf",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}
# 글꼴과 xterm 은 3MB 가 넘고 판이 고정이라 매번 새로 받을 까닭이 없다. 나머지는 고치면 바로 보이게 캐시하지 않는다.
CACHED = ("fonts/", "vendor/")

# 업데이트 알림. 레포 받기(fetch)는 Windows 쪽 git.exe 로 한다: 비공개 레포의 로그인 정보가 Windows 에 있다.
CONF = Path("/etc/chiios/chiios.conf")
VERSION = HERE.parent / "VERSION"
GIT_EXE = Path("/mnt/c/Program Files/Git/cmd/git.exe")
UPDATE_STATE = Path("/var/lib/chiios/update.json")
UPDATE_LOG = Path("/var/log/chiios-update.log")
CHECK_EVERY = 30 * 60
# 이 파일이 바뀐 판은 Debian 쪽 setup.sh 만으로는 반영되지 않는다(바로가기·자동 켜기·.wslconfig).
WINDOWS_SIDE = ("install.ps1", "autostart.ps1", "shortcut.ps1", "start.cmd", "wslconfig", "chiios.ico")
update = {"enabled": False, "reason": "아직 확인 전", "commits": [], "windows": [], "checkedAt": 0, "fetched": False}
update_lock = threading.Lock()


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    # 한쪽이 끊기면 양쪽을 다 닫아야 반대 방향 recv 도 깨어나 스레드가 끝난다.
    for s in (src, dst):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def sh(args, timeout=10):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def iso_ts(s):
    # docker 는 나노초까지 찍는데 fromisoformat 은 마이크로초까지만 읽는다.
    if not s or s.startswith("0001-"):
        return None
    s = s.rstrip("Z")
    if "." in s:
        head, frac = s.split(".", 1)
        s = head + "." + frac[:6]
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()


def day_start():
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def log_event(kind, text, bot=None, t=None):
    rec = {"t": t or time.time(), "kind": kind, "text": text, "bot": bot}
    with lock:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def bot_meta():
    try:
        return json.loads((BOTS_DIR / "bots.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bot_name(project):
    return bot_meta().get(project, {}).get("name", project)


def system_info():
    rel = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                rel[k] = v.strip('"')
    except OSError:
        pass
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0]) * 1024
    disk = shutil.disk_usage("/")
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    return {
        "os": f"{rel.get('NAME', 'Linux').split(' ')[0]} {rel.get('VERSION_ID', '')}".strip(),
        "host": socket.gethostname(),
        "user": os.environ.get("USER") or Path.home().name,
        "uptime": uptime,
        "memUsed": mem["MemTotal"] - mem.get("MemAvailable", 0),
        "memTotal": mem["MemTotal"],
        "diskUsed": disk.used,
        "diskTotal": disk.total,
    }


def services():
    code, out = sh(["systemctl", "is-active", "docker", "chii-term"])
    states = out.split()
    return {"docker": states[:1] == ["active"], "term": states[1:2] == ["active"]}


# compose 가 구운 이미지에는 project 라벨이 박혀서, 같은 이미지를 docker run 으로 잠깐 띄운 컨테이너도
# 봇으로 잡힌다(11-12 시험 때 오늘 기록에 가짜 '비서 깨어남' 이 찍혔다). 작업 폴더 라벨은 compose 로
# 띄운 컨테이너에만 붙으므로 그걸로 가린다.
BOT_LABEL = "label=com.docker.compose.project.working_dir"


def bots():
    code, out = sh(["docker", "ps", "-a", "--filter", BOT_LABEL, "--format", "{{.ID}}"])
    if code != 0:
        return None
    ids = out.split()
    if not ids:
        return []
    code, out = sh(["docker", "inspect", *ids])
    items = json.loads(out) if code == 0 else []
    meta = bot_meta()
    sizes = {}
    result = []
    for c in items:
        labels = c["Config"].get("Labels") or {}
        project = labels.get("com.docker.compose.project", "")
        workdir = labels.get("com.docker.compose.project.working_dir", "")
        st = c["State"]
        # 크기는 컨테이너가 기억하는 이미지 ID 가 아니라 이름(loa-bot:latest)으로 읽는다. 다시 구우면 이름이
        # 새 이미지로 넘어가고 옛 ID 는 지워져(Docker 29 containerd 저장소) ID 로는 못 찾는다.
        # 다음에 깨울 때 쓰이는 것도 이름이 가리키는 이미지다.
        img = c["Image"]
        ref = c["Config"].get("Image") or img
        if ref not in sizes:
            code, o = sh(["docker", "image", "inspect", ref, "--format", "{{.Id}} {{.Size}}"])
            parts = o.split()
            sizes[ref] = (parts[0], int(parts[1])) if code == 0 and len(parts) == 2 and parts[1].isdigit() else ("", None)
        ref_id, size = sizes[ref]
        commit = subject = ""
        if workdir:
            code, o = sh(["git", "-C", workdir, "log", "-1", "--format=%h%x09%s"])
            if code == 0 and "\t" in o:
                commit, subject = o.strip().split("\t", 1)
        m = meta.get(project, {})
        result.append({
            "project": project,
            "name": m.get("name", project),
            "container": c["Name"].lstrip("/"),
            "state": st["Status"],
            "exitCode": st["ExitCode"],
            "startedAt": iso_ts(st["StartedAt"]),
            "finishedAt": iso_ts(st["FinishedAt"]),
            "imageSize": size,
            # 일하는 중인데 이름이 다른 이미지를 가리키면, 새로 구운 판이 아직 안 올라간 것이다.
            "stale": st["Status"] == "running" and bool(ref_id) and ref_id != img,
            "commit": commit,
            "subject": subject,
            "guard": m.get("guard", ""),
            "baking": project in baking,
            "canBake": (BOTS_DIR / f"{project}.sh").exists(),
            "dir": workdir,
        })
    return sorted(result, key=lambda b: b["name"])


def find_bot(project):
    for b in bots() or []:
        if b["project"] == project:
            return b
    return None


def load_todos():
    try:
        return json.loads(TODOS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_todos(items):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TODOS.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(TODOS)


def visible_todos():
    # 끝낸 일은 그날 하루만 남긴다. 계속 쌓이면 남은 일이 묻힌다.
    since = day_start()
    return [t for t in load_todos() if not t.get("done") or (t.get("doneAt") or 0) >= since]


def add_todo(text):
    text = str(text or "").strip()[:200]
    if not text:
        return None
    item = {"id": uuid.uuid4().hex[:8], "text": text, "done": False, "createdAt": time.time(), "doneAt": None}
    with lock:
        items = load_todos()
        items.append(item)
        save_todos(items)
    return item


def change_todo(tid, op, done=None):
    """op 는 toggle·set·delete. 바뀐 항목을 돌려주고, 없으면 None."""
    found = finished = None
    with lock:
        items = load_todos()
        for t in items:
            if t["id"] != tid:
                continue
            found = t
            if op == "delete":
                items.remove(t)
            else:
                new = (not t["done"]) if op == "toggle" else bool(done)
                if new and not t["done"]:
                    finished = t["text"]
                t["done"] = new
                t["doneAt"] = (t.get("doneAt") or time.time()) if new else None
            break
        if found:
            save_todos(items)
    if finished:
        log_event("todo", f"할 일 끝 · {finished}")
    return found


def bot_act(bot, act):
    if act == "start":
        code, _ = sh(["docker", "compose", "--project-directory", bot["dir"], "up", "-d"], timeout=180)
    elif act == "stop":
        code, _ = sh(["docker", "compose", "--project-directory", bot["dir"], "stop"], timeout=120)
    elif act == "bake" and bot["canBake"]:
        bake(bot)
        code = 0
    else:
        code = 1
    return code == 0


def bot_logs(bot, tail):
    # 봇이 제 기록에 시각을 이미 찍으므로 docker 시각(--timestamps)은 붙이지 않는다.
    try:
        p = subprocess.run(["docker", "logs", "--tail", str(int(tail)), bot["container"]],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
        return p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def events():
    since = day_start()
    out = []
    code, o = sh(["journalctl", "--list-boots", "-o", "json", "--no-pager"])
    if code == 0:
        try:
            boots = json.loads(o)
        except ValueError:
            boots = []
        for b in boots:
            first = (b.get("first_entry") or 0) / 1e6
            last = (b.get("last_entry") or 0) / 1e6
            if first >= since:
                out.append({"t": first, "kind": "boot", "text": "Debian 깨어남"})
            if b.get("index") != 0 and last >= since:
                out.append({"t": last, "kind": "down", "text": "Debian 꺼짐"})
    try:
        with EVENTS.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("t", 0) >= since:
                    out.append(rec)
    except OSError:
        pass
    out.sort(key=lambda e: e["t"])
    return out[-30:]


def watch_docker():
    # 봇이 깨고 자고 쓰러진 일을 기록에 남긴다. docker 는 사건을 메모리에만 들고 있어서
    # 들을 때 받아 적지 않으면 다음 재시작 때 사라진다.
    kills = {}
    while True:
        try:
            p = subprocess.Popen(
                ["docker", "events", "--filter", "type=container", "--filter", BOT_LABEL,
                 "--format", "{{json .}}"],
                stdout=subprocess.PIPE, text=True)
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                act = ev.get("Action") or ev.get("status") or ""
                attrs = (ev.get("Actor") or {}).get("Attributes") or {}
                project = attrs.get("com.docker.compose.project", "")
                name = bot_name(project)
                t = ev.get("time") or time.time()
                if act == "start":
                    log_event("start", f"{name} 깨어남", project, t)
                elif act == "kill":
                    kills[project] = t
                elif act == "stop":
                    log_event("stop", f"{name} 재움", project, t)
                elif act == "die" and t - kills.get(project, 0) > 30:
                    code = attrs.get("exitCode", "?")
                    if code == "0":
                        log_event("stop", f"{name} 스스로 멈춤", project, t)
                    else:
                        log_event("crash", f"{name} 쓰러짐 (exit {code})", project, t)
        except OSError:
            pass
        time.sleep(5)


def read_conf():
    out = {}
    try:
        for line in CONF.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def wingit(winrepo, *args, timeout=60):
    try:
        p = subprocess.run([str(GIT_EXE), "-C", winrepo, *args], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def check_update(fetch=True):
    """새 판이 있는지 본다. 결과는 update 에 담아 두고 /api/state 는 이걸 읽기만 한다(요청마다 git 을 돌리지 않게)."""
    with update_lock:
        repo = read_conf().get("CHII_REPO", "")
        if not repo or not GIT_EXE.exists():
            update.update(enabled=False, reason="Windows 쪽 git 이 없어 새 판을 볼 수 없다", commits=[], windows=[])
            return dict(update)
        try:
            winrepo = subprocess.run(["wslpath", "-w", repo], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            winrepo = ""
        if not winrepo:
            update.update(enabled=False, reason="레포 자리를 Windows 경로로 못 바꿨다", commits=[], windows=[])
            return dict(update)
        fetched = update["fetched"]
        if fetch:
            code, _ = wingit(winrepo, "fetch", "--quiet")
            fetched = code == 0
        try:
            deployed = VERSION.read_text().strip()
        except OSError:
            deployed = ""
        code, upstream = wingit(winrepo, "rev-parse", "@{u}", timeout=15)
        upstream = upstream.strip()
        commits, windows = [], []
        if code == 0 and upstream and deployed and deployed != upstream:
            code, log = wingit(winrepo, "log", "--format=%h%x09%s", f"{deployed}..{upstream}", timeout=15)
            for line in log.splitlines():
                if "\t" in line:
                    sha, subject = line.split("\t", 1)
                    commits.append({"sha": sha, "subject": subject})
            code, names = wingit(winrepo, "diff", "--name-only", f"{deployed}..{upstream}", timeout=15)
            windows = sorted({n for n in names.split() if n in WINDOWS_SIDE})
        update.update(enabled=True, reason="", deployed=deployed, upstream=upstream, commits=commits,
                      windows=windows, checkedAt=time.time(), fetched=fetched)
        return dict(update)


def update_progress():
    try:
        st = json.loads(UPDATE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    # 업데이트 도중 PC 가 꺼지면 '하는 중' 이 영영 남는다. setup.sh 가 30분을 넘길 일은 없으니 멈춘 걸로 본다.
    if st.get("state") == "running" and time.time() - st.get("t", 0) > 1800:
        st = {**st, "state": "fail", "msg": "업데이트가 중간에 멈춘 것 같다. 다시 해 본다"}
    tail = ""
    if st.get("state") == "fail":
        try:
            tail = "\n".join(UPDATE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-15:])
        except OSError:
            pass
    return {**st, "tail": tail}


def watch_update():
    # 시작하자마자 한 번, 그 뒤로 30분마다. 데스크톱을 Parsec 으로 열었을 때 새 판이 바로 보이게.
    while True:
        try:
            check_update()
        except Exception:  # 확인이 한 번 실패해도 다음 확인은 해야 한다.
            pass
        time.sleep(CHECK_EVERY)


def start_update():
    # root 로 돌아야 setup.sh 를 다시 돌릴 수 있다. WSL 의 chiiOS 사용자는 sudo 비밀번호가 없다(setup.sh).
    # systemd-run 으로 띄워 따로 된 작업으로 만든다: setup.sh 가 이 서버를 다시 켜도 업데이트는 이어 간다.
    try:
        p = subprocess.run(["sudo", "-n", "systemd-run", "--unit=chii-update", "--collect", "--quiet",
                            "/usr/local/sbin/chii-update"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()
        if "already" in err or "exists" in err:
            return False, "이미 업데이트하는 중이다"
        return False, err[:200] or "sudo 가 막혔다. 터미널에서 sudo chii-update"
    return True, None


def bake(bot):
    project = bot["project"]
    if project in baking:
        return
    baking[project] = time.time()

    def work():
        try:
            p = subprocess.run(["bash", str(BOTS_DIR / f"{project}.sh")], capture_output=True, text=True, timeout=1800)
            if p.returncode == 0:
                log_event("bake", f"{bot['name']} 다시 구움", project)
            else:
                last = ((p.stderr or p.stdout).strip().splitlines() or ["?"])[-1]
                log_event("bakefail", f"{bot['name']} 굽기 실패 · {last[:120]}", project)
        except subprocess.TimeoutExpired:
            log_event("bakefail", f"{bot['name']} 굽기 실패 · 30분 넘게 걸려 멈춤", project)
        finally:
            baking.pop(project, None)

    threading.Thread(target=work, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "chiiOS"

    def log_message(self, *args):
        pass

    def host_ok(self):
        # localhost 이름으로만 받는다. 다른 이름이 이 주소를 가리키게 해서 들어오는 우회(DNS rebinding)를 막는다.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("localhost", "127.0.0.1")

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        if not self.host_ok():
            return self.send_error(403)
        u = urlparse(self.path)
        if u.path == "/term/ws":
            return self.term_ws()
        if u.path == "/api/state":
            return self.send_json({
                "sys": system_info(),
                "services": services(),
                "bots": bots(),
                "todos": visible_todos(),
                "events": events(),
                "termPort": TERM_PORT,
                "update": {"enabled": update["enabled"], "count": len(update["commits"]),
                           "state": update_progress().get("state", "")},
            })
        m = re.fullmatch(r"/api/bots/([\w.-]+)/logs", u.path)
        if m:
            bot = find_bot(m.group(1))
            if not bot:
                return self.send_json({"error": "그런 봇이 없다"}, 404)
            tail = parse_qs(u.query).get("tail", ["200"])[0]
            return self.send_json({"name": bot["name"], "text": bot_logs(bot, tail if tail.isdigit() else 200)})
        if u.path == "/api/assistant":
            return self.assistant("GET", "/status")
        if u.path == "/api/update":
            return self.send_json({**update, "progress": update_progress()})
        return self.static(u.path)

    def static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self.send_error(404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "max-age=604800" if rel.startswith(CACHED) else "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def term_ws(self):
        # 터미널 칸의 웹소켓을 ttyd 로 바이트 그대로 잇는다. 홈 화면과 같은 출처로 붙어야 칸 안의 글꼴·색·단축키를
        # 홈 화면이 쥘 수 있다(ttyd 페이지를 iframe 으로 넣으면 출처가 달라 손댈 수 없었다).
        # 셸을 내주는 길이라 출처는 여기서 홈 화면 것만 받는다. 다른 사이트의 페이지는 Origin 을 꾸밀 수 없다.
        # ttyd 의 --check-origin 은 Origin 과 Host 가 같은지를 보므로, 넘길 때는 둘 다 ttyd 자기 주소로 맞춘다.
        origin = self.headers.get("Origin", "")
        if origin not in (f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}") \
                or (self.headers.get("Upgrade") or "").lower() != "websocket":
            return self.send_error(403)
        try:
            up = socket.create_connection(("127.0.0.1", TERM_PORT), timeout=5)
        except OSError:
            return self.send_error(502)
        head = [
            "GET /ws HTTP/1.1",
            f"Host: localhost:{TERM_PORT}",
            f"Origin: http://localhost:{TERM_PORT}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {self.headers.get('Sec-WebSocket-Key', '')}",
            f"Sec-WebSocket-Version: {self.headers.get('Sec-WebSocket-Version', '13')}",
            "Sec-WebSocket-Protocol: tty",
        ]
        up.sendall(("\r\n".join(head) + "\r\n\r\n").encode("ascii"))
        up.settimeout(None)
        self.connection.settimeout(None)
        self.close_connection = True
        # ttyd 의 101 응답부터 그대로 돌려준다. 키가 같으니 브라우저가 보는 Accept 값도 맞는다.
        back = threading.Thread(target=pipe, args=(up, self.connection), daemon=True)
        back.start()
        pipe(self.connection, up)
        back.join()
        up.close()

    def do_POST(self):
        # 커스텀 머리글을 요구하면 다른 사이트에서 몰래 보내는 요청은 브라우저가 사전 확인에서 막는다.
        if not self.host_ok() or self.headers.get("X-Chii") != "1":
            return self.send_error(403)
        u = urlparse(self.path)
        data = self.body()

        m = re.fullmatch(r"/api/bots/([\w.-]+)/(start|stop|bake)", u.path)
        if m:
            bot = find_bot(m.group(1))
            if not bot:
                return self.send_json({"error": "그런 봇이 없다"}, 404)
            act = m.group(2)
            if act == "start" and bot["guard"] and not data.get("confirm"):
                return self.send_json({"guard": bot["guard"]}, 409)
            if act == "bake" and not bot["canBake"]:
                return self.send_json({"error": "굽는 스크립트가 없다"}, 400)
            ok = bot_act(bot, act)
            return self.send_json({"ok": ok}, 200 if ok else 500)

        if u.path == "/api/todos":
            item = add_todo(data.get("text"))
            if not item:
                return self.send_json({"error": "빈 할 일"}, 400)
            return self.send_json({"ok": True, "item": item})

        # set 은 비서용: 누를 때마다 뒤집히는 toggle 과 달리 끝냈다/안 했다를 정해서 준다.
        m = re.fullmatch(r"/api/todos/(\w+)/(toggle|delete|set)", u.path)
        if m:
            if m.group(2) == "set" and not isinstance(data.get("done"), bool):
                return self.send_json({"error": "done 은 true/false"}, 400)
            item = change_todo(m.group(1), m.group(2), data.get("done"))
            if not item:
                return self.send_json({"error": "그런 할 일이 없다"}, 404)
            return self.send_json({"ok": True, "item": item})

        if u.path == "/api/update/check":
            return self.send_json(check_update())
        if u.path == "/api/update":
            ok, err = start_update()
            return self.send_json({"ok": True} if ok else {"error": err}, 200 if ok else 409)

        if u.path in ("/api/assistant/key", "/api/assistant/clear", "/api/assistant/chat", "/api/assistant/brief"):
            return self.assistant("POST", "/" + u.path.rsplit("/", 1)[1], data, stream=u.path.endswith("/chat"))

        return self.send_error(404)

    def assistant(self, method, path, body=None, stream=False):
        # 비서는 따로 도는 봇(bots/assistant)이다. 홈 화면은 말을 넘겨주기만 하고, 비서 문(7683)은
        # 브라우저에 직접 내주지 않는다. 출처 검사를 홈 화면 한곳에서만 하려고.
        try:
            conn = http.client.HTTPConnection("127.0.0.1", ASSIST_PORT, timeout=600 if stream else 30)
            conn.request(method, path, body=None if body is None else json.dumps(body),
                         headers={"Host": "localhost", "X-Chii": "1", "Content-Type": "application/json"})
            resp = conn.getresponse()
        except OSError:
            if path == "/status":
                return self.send_json({"down": True, "missing": find_bot(ASSIST_PROJECT) is None})
            return self.send_json({"error": "비서가 자고 있어. 깨워 줘."}, 503)
        if not stream or resp.status != 200:
            data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.getheader("Content-Type", "application/json"))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            conn.close()
            return None
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.close_connection = True
        # 줄이 오는 대로 바로 넘긴다. 모아서 넘기면 답이 한꺼번에 툭 떨어진다.
        try:
            for line in resp:
                self.wfile.write(line)
        except OSError:
            # 화면을 닫아도 비서는 대화를 끝까지 마치고 기록에 남긴다.
            pass
        conn.close()
        return None


def main():
    threading.Thread(target=watch_docker, daemon=True).start()
    threading.Thread(target=watch_update, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
