# 비서 봇의 문(127.0.0.1:7683). 홈 화면 서버만 이 문을 두드린다.
# Windows 쪽 브라우저에서도 이 주소가 열리므로, 홈 화면처럼 Host 와 X-Chii 머리글을 보고 다른 사이트의 요청을 막는다.
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from assistant import Assistant, say

PORT = int(os.environ.get("ASSIST_PORT", "7683"))
A = Assistant(os.environ.get("ASSIST_DATA", "/data"))


class Handler(BaseHTTPRequestHandler):
    server_version = "chiiOS-assistant"

    def log_message(self, *args):
        pass

    def allowed(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("localhost", "127.0.0.1") and self.headers.get("X-Chii") == "1"

    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
        if not self.allowed():
            return self.send_error(403)
        if self.path == "/status":
            return self.send_json(A.status())
        return self.send_error(404)

    def do_POST(self):
        if not self.allowed():
            return self.send_error(403)
        data = self.body()
        if self.path == "/key":
            ok, err = A.save_key(data.get("key"))
            return self.send_json({"ok": True} if ok else {"error": err}, 200 if ok else 400)
        if self.path == "/clear":
            A.clear()
            return self.send_json({"ok": True})
        if self.path == "/brief":
            rec = A.morning()
            return self.send_json({"ok": bool(rec)}, 200 if rec else 409)
        if self.path == "/chat":
            text = str(data.get("text", "")).strip()[:4000]
            if not text:
                return self.send_json({"error": "빈 말"}, 400)
            # 답을 글자가 나오는 대로 한 줄짜리 JSON 으로 흘려보낸다. 길이를 모르니 끝은 연결을 닫아 알린다(HTTP/1.0).
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.end_headers()
            self.close_connection = True

            def emit(obj):
                try:
                    self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                except OSError:
                    # 화면을 닫아도 대화는 끝까지 가서 기록에 남는다. 다음에 열면 보인다.
                    pass

            A.chat(text, emit)
            return None
        return self.send_error(404)


def morning_loop():
    # 1분마다 아침 보고 때가 됐는지 본다. 시각을 딱 맞춰 재우는 대신 이렇게 하면 PC 가 그 시각에
    # 꺼져 있었어도 켜진 뒤 바로 따라잡는다.
    while True:
        try:
            if A.brief_due():
                A.morning()
        except Exception as e:  # 한 번 실패해도 다음 날 보고는 해야 한다.
            say(f"아침 보고 실패 · {type(e).__name__}: {e}")
        time.sleep(60)


if __name__ == "__main__":
    say(f"하치와레 깨어남 · 127.0.0.1:{PORT} · {A.status()['model']} · 열쇠 {'있음' if A.read_key() else '없음'}")
    threading.Thread(target=morning_loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
