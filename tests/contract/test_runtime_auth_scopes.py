import os
import tempfile
import time
import unittest

import requests

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer


def echo_text(text: str) -> str:
    return f"echo:{text}"


ECHO_SCHEMA = {
    "name": "echo_text",
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
}


class RuntimeAuthScopesContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-auth-contract-", suffix=".db")
        os.close(fd)

        state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        executor = AsyncLocalExecutor(state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=state_manager,
            scoped_bearer_tokens={
                "writer-token": {"actor_id": "writer", "scopes": ["runs:execute", "runs:read"]},
                "reader-token": {"actor_id": "reader", "scopes": ["runs:read"]},
            },
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_execute_requires_runs_execute_scope(self) -> None:
        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer reader-token"},
            json={
                "macro": {
                    "steps": [
                        {
                            "step_id": "step_1",
                            "tool_name": "echo_text",
                            "arguments": {"text": "hello"},
                        }
                    ]
                }
            },
            timeout=5,
        )
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertEqual(payload["error_type"], "forbidden")
        self.assertIn("runs:execute", payload["message"])


if __name__ == "__main__":
    unittest.main()
