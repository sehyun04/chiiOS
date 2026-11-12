# 비서 봇의 문(127.0.0.1:7683). 홈 화면 서버만 이 문을 두드린다.
# Windows 쪽 브라우저에서도 이 주소가 열리므로, 홈 화면처럼 Host 와 X-Chii 머리글을 보고 다른 사이트의 요청을 막는다.
import json
import os
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


if __name__ == "__main__":
    say(f"비서 깨어남 · 127.0.0.1:{PORT} · {A.status()['model']} · 열쇠 {'있음' if A.read_key() else '없음'}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
