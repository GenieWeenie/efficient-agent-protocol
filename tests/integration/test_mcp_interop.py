import json
import os
import sys
import tempfile
import time
import unittest

import requests

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import INVOKE_MCP_TOOL_SCHEMA, invoke_mcp_tool
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer


class MCPInteropIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-mcp-interop-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("invoke_mcp_tool", invoke_mcp_tool, INVOKE_MCP_TOOL_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="secret-token",
        ).start()
        time.sleep(0.05)

        self.mock_server_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "fixtures", "mock_mcp_stdio_server.py")
        )

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_runtime_executes_reference_mcp_tool(self) -> None:
        self.assertTrue(os.path.exists(self.mock_server_path))
        server_command = f"{sys.executable} -u {self.mock_server_path}"
        execute_response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
            json={
                "macro": {
                    "steps": [
                        {
                            "step_id": "step_mcp",
                            "tool_name": "invoke_mcp_tool",
                            "arguments": {
                                "server_command": server_command,
                                "tool_name": "echo_upper",
                                "tool_arguments": {"text": "hello mcp"},
                                "timeout_seconds": 10,
                                "require_listed_tool": True,
                            },
                        }
                    ]
                }
            },
            timeout=10,
        )
        self.assertEqual(execute_response.status_code, 200)
        body = execute_response.json()
        pointer_id = body["pointer_id"]
        raw_output = self.state_manager.retrieve(pointer_id)
        payload = json.loads(raw_output)
        self.assertEqual(payload["content"][0]["type"], "text")
        self.assertEqual(payload["content"][0]["text"], "HELLO MCP")
        self.assertFalse(payload.get("isError", False))

        run_id = body["metadata"]["execution_run_id"]
        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
