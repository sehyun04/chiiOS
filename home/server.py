#!/usr/bin/env python3
# chiiOS 홈 화면. 봇·할 일·기록을 보여 주고, 터미널 칸에는 ttyd 를 띄운다.
# 표준 라이브러리만 쓴다. 봇 돌리는 기계에 pip 패키지를 들이면 setup.sh 가 챙길 것이 늘고 업데이트 때 깨질 곳도 는다.
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

TODOS = STATE_DIR / "todos.json"
EVENTS = STATE_DIR / "events.jsonl"
lock = threading.Lock()
baking = {}

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
}


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


def bots():
    code, out = sh(["docker", "ps", "-a", "--filter", "label=com.docker.compose.project", "--format", "{{.ID}}"])
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
                ["docker", "events", "--filter", "type=container", "--filter", "label=com.docker.compose.project",
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
        if u.path == "/api/state":
            return self.send_json({
                "sys": system_info(),
                "services": services(),
                "bots": bots(),
                "todos": visible_todos(),
                "events": events(),
                "termPort": TERM_PORT,
            })
        m = re.fullmatch(r"/api/bots/([\w.-]+)/logs", u.path)
        if m:
            bot = find_bot(m.group(1))
            if not bot:
                return self.send_json({"error": "그런 봇이 없다"}, 404)
            tail = parse_qs(u.query).get("tail", ["200"])[0]
            tail = tail if tail.isdigit() else "200"
            # 봇이 제 기록에 시각을 이미 찍으므로 docker 시각(--timestamps)은 붙이지 않는다.
            p = subprocess.run(["docker", "logs", "--tail", tail, bot["container"]],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
            return self.send_json({"name": bot["name"], "text": p.stdout})
        return self.static(u.path)

    def static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        f = (STATIC / rel).resolve()
        if STATIC.resolve() not in f.parents or not f.is_file():
            return self.send_error(404)
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(f.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
            if act == "start":
                if bot["guard"] and not data.get("confirm"):
                    return self.send_json({"guard": bot["guard"]}, 409)
                code, out = sh(["docker", "compose", "--project-directory", bot["dir"], "up", "-d"], timeout=180)
            elif act == "stop":
                code, out = sh(["docker", "compose", "--project-directory", bot["dir"], "stop"], timeout=120)
            else:
                if not bot["canBake"]:
                    return self.send_json({"error": "굽는 스크립트가 없다"}, 400)
                bake(bot)
                code = 0
            return self.send_json({"ok": code == 0}, 200 if code == 0 else 500)

        if u.path == "/api/todos":
            text = str(data.get("text", "")).strip()[:200]
            if not text:
                return self.send_json({"error": "빈 할 일"}, 400)
            with lock:
                items = load_todos()
                items.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False,
                              "createdAt": time.time(), "doneAt": None})
                save_todos(items)
            return self.send_json({"ok": True})

        m = re.fullmatch(r"/api/todos/(\w+)/(toggle|delete)", u.path)
        if m:
            done_text = None
            with lock:
                items = load_todos()
                for t in items:
                    if t["id"] == m.group(1):
                        if m.group(2) == "delete":
                            items.remove(t)
                        else:
                            t["done"] = not t["done"]
                            t["doneAt"] = time.time() if t["done"] else None
                            done_text = t["text"] if t["done"] else None
                        break
                save_todos(items)
            if done_text:
                log_event("todo", f"할 일 끝 · {done_text}")
            return self.send_json({"ok": True})

        return self.send_error(404)


def main():
    threading.Thread(target=watch_docker, daemon=True).start()
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
