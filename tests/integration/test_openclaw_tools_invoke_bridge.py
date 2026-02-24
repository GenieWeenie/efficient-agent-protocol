import json
import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Dict

import requests

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import INVOKE_OPENCLAW_TOOL_SCHEMA, invoke_openclaw_tool
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer


def _json_response(handler: BaseHTTPRequestHandler, status_code: int, payload: Dict[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


class _MockOpenClawToolsInvokeHandler(BaseHTTPRequestHandler):
    server: "_MockOpenClawHTTPServer"

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/tools/invoke":
            _json_response(self, 404, {"error": {"code": "NOT_FOUND", "message": "Route not found."}})
            return

        auth_header = (self.headers.get("Authorization") or "").strip()
        if auth_header != f"Bearer {self.server.required_token}":
            _json_response(
                self,
                401,
                {"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid bearer token."}},
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            _json_response(
                self,
                400,
                {"error": {"code": "BAD_REQUEST", "message": "Invalid Content-Length header."}},
            )
            return

        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _json_response(
                self,
                400,
                {"error": {"code": "BAD_REQUEST", "message": "Request body must be valid JSON."}},
            )
            return

        tool_name = payload.get("name")
        arguments = payload.get("arguments", {})
        if tool_name == "blocked_tool":
            _json_response(
                self,
                403,
                {
                    "error": {
                        "code": "TOOL_INVOKE_POLICY_DENIED",
                        "message": "Tool denied by policy.",
                        "details": {"policy": "denylist"},
                    }
                },
            )
            return

        _json_response(
            self,
            200,
            {"ok": True, "tool": tool_name, "arguments": arguments},
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


class _MockOpenClawHTTPServer(ThreadingHTTPServer):
    def __init__(self, required_token: str):
        super().__init__(("127.0.0.1", 0), _MockOpenClawToolsInvokeHandler)
        self.required_token = required_token
        self._thread = Thread(target=self.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def start(self) -> "_MockOpenClawHTTPServer":
        self._thread.start()
        return self

    def stop(self) -> None:
        self.shutdown()
        self.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=5)


class OpenClawToolsInvokeBridgeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-openclaw-tools-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("invoke_openclaw_tool", invoke_openclaw_tool, INVOKE_OPENCLAW_TOOL_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.runtime_server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="runtime-token",
        ).start()
        self.openclaw_server = _MockOpenClawHTTPServer(required_token="gateway-token").start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.runtime_server.stop()
        self.openclaw_server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _execute_bridge_step(self, api_key: str, tool_name: str) -> Dict[str, Any]:
        response = requests.post(
            f"{self.runtime_server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer runtime-token"},
            json={
                "macro": {
                    "steps": [
                        {
                            "step_id": "step_openclaw",
                            "tool_name": "invoke_openclaw_tool",
                            "arguments": {
                                "base_url": self.openclaw_server.base_url,
                                "api_key": api_key,
                                "tool_name": tool_name,
                                "tool_arguments": {"text": "hello"},
                                "timeout_seconds": 10,
                            },
                        }
                    ]
                }
            },
            timeout=10,
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_runtime_bridge_executes_openclaw_tool_successfully(self) -> None:
        body = self._execute_bridge_step(api_key="gateway-token", tool_name="echo_tool")
        payload = json.loads(self.state_manager.retrieve(body["pointer_id"]))
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool"], "echo_tool")
        self.assertEqual(payload["arguments"]["text"], "hello")

    def test_runtime_bridge_surfaces_auth_failure(self) -> None:
        body = self._execute_bridge_step(api_key="wrong-token", tool_name="echo_tool")
        self.assertEqual(body["metadata"]["status"], "error")
        self.assertEqual(body["metadata"]["error_type"], "tool_execution_error")

        run_id = body["metadata"]["execution_run_id"]
        run_response = requests.get(
            f"{self.runtime_server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer runtime-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        failed_events = [
            event
            for event in run_response.json()["trace_events"]
            if event.get("event_type") == "failed"
        ]
        self.assertEqual(len(failed_events), 1)
        self.assertIn("unauthorized", failed_events[0]["error"]["message"].lower())

    def test_runtime_bridge_surfaces_policy_denial(self) -> None:
        body = self._execute_bridge_step(api_key="gateway-token", tool_name="blocked_tool")
        self.assertEqual(body["metadata"]["status"], "error")
        self.assertEqual(body["metadata"]["error_type"], "tool_execution_error")

        run_id = body["metadata"]["execution_run_id"]
        run_response = requests.get(
            f"{self.runtime_server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer runtime-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        failed_events = [
            event
            for event in run_response.json()["trace_events"]
            if event.get("event_type") == "failed"
        ]
        self.assertEqual(len(failed_events), 1)
        self.assertIn("policy_denied", failed_events[0]["error"]["message"].lower())


if __name__ == "__main__":
    unittest.main()
