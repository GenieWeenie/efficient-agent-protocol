import json
import sys
from typing import Any, Dict, Optional


def _read_message() -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    try:
        content_length = int(headers.get("content-length", "0"))
    except ValueError:
        content_length = 0
    if content_length <= 0:
        return None

    payload = sys.stdin.buffer.read(content_length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def _write_message(payload: Dict[str, Any]) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("utf-8"))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _reply(request: Dict[str, Any], result: Dict[str, Any]) -> None:
    if "id" not in request:
        return
    _write_message({"jsonrpc": "2.0", "id": request["id"], "result": result})


def _reply_error(request: Dict[str, Any], code: int, message: str) -> None:
    if "id" not in request:
        return
    _write_message({"jsonrpc": "2.0", "id": request["id"], "error": {"code": code, "message": message}})


def main() -> int:
    while True:
        request = _read_message()
        if request is None:
            return 0

        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            _reply(
                request,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mock-mcp-stdio", "version": "0.0.1"},
                },
            )
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            _reply(
                request,
                {
                    "tools": [
                        {
                            "name": "echo_upper",
                            "description": "Return uppercase text.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"text": {"type": "string"}},
                                "required": ["text"],
                                "additionalProperties": False,
                            },
                        }
                    ]
                },
            )
            continue

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if tool_name != "echo_upper":
                _reply_error(request, -32602, f"Unknown tool '{tool_name}'.")
                continue
            text = str(arguments.get("text", ""))
            _reply(
                request,
                {
                    "content": [{"type": "text", "text": text.upper()}],
                    "isError": False,
                },
            )
            continue

        _reply_error(request, -32601, f"Unknown method '{method}'.")


if __name__ == "__main__":
    raise SystemExit(main())
