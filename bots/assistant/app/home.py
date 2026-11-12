# 홈 화면 서버(chii-home) API 를 부르는 쪽. 할 일·봇 단추·상태는 홈 화면이 쥐고 있고 비서는 부탁만 한다.
# 비서가 Docker 를 직접 만지지 않으니, 니나브 깨우기 전 확인 같은 규칙이 홈 화면 한곳에만 있으면 된다.
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("CHII_HOME_URL", "http://127.0.0.1:7682")


def _json(raw):
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


def call(method, path, body=None, timeout=30):
    """(HTTP 상태, JSON). 홈 화면에 닿지 못하면 상태 0."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"X-Chii": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _json(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _json(e.read())
    except (urllib.error.URLError, OSError) as e:
        return 0, {"error": f"홈 화면에 안 닿음 ({e})"}


def q(s):
    return urllib.parse.quote(str(s), safe="")


def state():
    code, data = call("GET", "/api/state")
    return data if code == 200 else None


def add_todo(text):
    return call("POST", "/api/todos", {"text": text})


def set_todo(tid, done):
    return call("POST", f"/api/todos/{q(tid)}/set", {"done": done})


def delete_todo(tid):
    return call("POST", f"/api/todos/{q(tid)}/delete")


def bot(project, act):
    # 깨우기는 docker compose up 이 끝날 때까지 기다리므로 넉넉히 둔다(홈 화면 쪽 상한 180초).
    return call("POST", f"/api/bots/{q(project)}/{act}", timeout=200)


def logs(project, tail):
    return call("GET", f"/api/bots/{q(project)}/logs?tail={int(tail)}")
