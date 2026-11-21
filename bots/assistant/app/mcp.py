# 하치와레 도구를 Claude Code 에 내주는 MCP 서버(Streamable HTTP 중 요청 하나에 JSON 답 하나인 가장 작은 모양).
# 머리인 Claude Code 는 Windows 쪽에서 돌아서 이 컨테이너의 함수를 직접 부를 수 없다. 대신 127.0.0.1 의 이 문으로 부른다.
import json

SERVER = {"name": "chii", "version": "1"}
# 클라이언트가 말한 판을 그대로 돌려준다. 도구만 쓰는 이 서버에선 판마다 달라지는 데가 없다.
FALLBACK_VERSION = "2025-06-18"


def handle(msg, tools, call):
    """JSON-RPC 메시지 하나를 처리한다. 알림(id 없음)이면 None.
    tools: [{name, description, input_schema}], call(name, args) -> (text, is_error)"""
    if not isinstance(msg, dict):
        return error(None, -32600, "잘못된 요청")
    mid = msg.get("id")
    method = msg.get("method")
    if mid is None:
        return None
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion") or FALLBACK_VERSION
        return result(mid, {"protocolVersion": ver, "capabilities": {"tools": {}}, "serverInfo": SERVER})
    if method == "ping":
        return result(mid, {})
    if method == "tools/list":
        return result(mid, {"tools": [{"name": t["name"], "description": t["description"],
                                       "inputSchema": t["input_schema"]} for t in tools]})
    if method == "tools/call":
        p = msg.get("params") or {}
        text, bad = call(str(p.get("name") or ""), p.get("arguments") or {})
        return result(mid, {"content": [{"type": "text", "text": text}], "isError": bool(bad)})
    return error(mid, -32601, f"{method} 는 없다")


def result(mid, obj):
    return {"jsonrpc": "2.0", "id": mid, "result": obj}


def error(mid, code, text):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
