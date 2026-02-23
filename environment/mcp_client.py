import json
import os
import select
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional


class MCPClientError(RuntimeError):
    """Raised when MCP transport/protocol interactions fail."""


class MCPStdioClient:
    """Minimal stdio MCP client for tools/list and tools/call."""

    def __init__(
        self,
        server_command: str,
        timeout_seconds: int = 30,
        working_directory: Optional[str] = None,
    ) -> None:
        self.server_command = server_command
        self.timeout_seconds = timeout_seconds
        self.working_directory = working_directory
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0

    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def start(self) -> None:
        if self._process is not None:
            return
        command_parts = shlex.split(self.server_command)
        if not command_parts:
            raise MCPClientError("MCP server_command must not be empty.")

        self._process = subprocess.Popen(
            command_parts,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.working_directory or None,
        )
        self.initialize()

    def close(self) -> None:
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1.0)
        self._process = None

    def initialize(self) -> Dict[str, Any]:
        payload = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "eap-mcp-bridge", "version": "0.1.0"},
        }
        response = self.request("initialize", payload)
        self.notify("notifications/initialized", {})
        return response

    def list_tools(self) -> Dict[str, Any]:
        return self.request("tools/list", {})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

    def notify(self, method: str, params: Dict[str, Any]) -> None:
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write_message(message)

    def request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._write_message(message)

        deadline = time.time() + float(self.timeout_seconds)
        while True:
            incoming = self._read_message(deadline=deadline)
            if "id" not in incoming:
                continue
            if incoming.get("id") != request_id:
                continue
            if "error" in incoming:
                raise MCPClientError(f"MCP error response: {incoming['error']}")
            return incoming.get("result", {})

    def _write_message(self, payload: Dict[str, Any]) -> None:
        process = self._require_process()
        if process.stdin is None:
            raise MCPClientError("MCP process stdin is unavailable.")

        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        framed = f"Content-Length: {len(raw)}\r\n\r\n".encode("utf-8") + raw
        process.stdin.write(framed)
        process.stdin.flush()

    def _read_message(self, deadline: float) -> Dict[str, Any]:
        process = self._require_process()
        if process.stdout is None:
            raise MCPClientError("MCP process stdout is unavailable.")

        header = self._read_until(process.stdout.fileno(), b"\r\n\r\n", deadline)
        if not header:
            raise MCPClientError("MCP server closed stream before header.")
        header_text = header.decode("utf-8", errors="replace")
        content_length = self._parse_content_length(header_text)
        body = self._read_exact(process.stdout.fileno(), content_length, deadline)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MCPClientError(f"Failed to decode MCP message: {str(exc)}") from exc

    @staticmethod
    def _parse_content_length(header_text: str) -> int:
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                _, value = line.split(":", 1)
                return int(value.strip())
        raise MCPClientError("Missing Content-Length header from MCP message.")

    @staticmethod
    def _read_until(fd: int, delimiter: bytes, deadline: float) -> bytes:
        data = bytearray()
        while delimiter not in data:
            if time.time() > deadline:
                raise MCPClientError("Timed out waiting for MCP response header.")
            timeout = max(0.0, deadline - time.time())
            readable, _, _ = select.select([fd], [], [], timeout)
            if not readable:
                continue
            chunk = os.read(fd, 1)
            if not chunk:
                break
            data.extend(chunk)
        return bytes(data)

    @staticmethod
    def _read_exact(fd: int, byte_count: int, deadline: float) -> bytes:
        data = bytearray()
        while len(data) < byte_count:
            if time.time() > deadline:
                raise MCPClientError("Timed out waiting for MCP response body.")
            timeout = max(0.0, deadline - time.time())
            readable, _, _ = select.select([fd], [], [], timeout)
            if not readable:
                continue
            chunk = os.read(fd, byte_count - len(data))
            if not chunk:
                raise MCPClientError("MCP server closed stream before full response body.")
            data.extend(chunk)
        return bytes(data)

    def _require_process(self) -> subprocess.Popen:
        if self._process is None:
            raise MCPClientError("MCP client not started.")
        if self._process.poll() is not None:
            raise MCPClientError("MCP server process exited unexpectedly.")
        return self._process


def invoke_mcp_tool_stdio(
    server_command: str,
    tool_name: str,
    tool_arguments: Dict[str, Any],
    timeout_seconds: int = 30,
    working_directory: Optional[str] = None,
    require_listed_tool: bool = True,
) -> Dict[str, Any]:
    """Execute an MCP tool call through a stdio server command."""

    with MCPStdioClient(
        server_command=server_command,
        timeout_seconds=timeout_seconds,
        working_directory=working_directory,
    ) as client:
        if require_listed_tool:
            listed = client.list_tools()
            tools: List[Dict[str, Any]] = listed.get("tools", [])
            available_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
            if tool_name not in available_names:
                raise MCPClientError(
                    f"MCP tool '{tool_name}' is not advertised by server. "
                    f"Available tools: {sorted(name for name in available_names if name)}"
                )
        return client.call_tool(tool_name=tool_name, arguments=tool_arguments)
