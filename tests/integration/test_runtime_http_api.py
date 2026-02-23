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
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
        "additionalProperties": False,
    },
}


class RuntimeHttpApiIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-runtime-api-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="secret-token",
        ).start()
        # Small startup buffer for thread scheduling stability in CI.
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_execute_macro_and_fetch_run_and_pointer_summary(self) -> None:
        execute_response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
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
        self.assertEqual(execute_response.status_code, 200)
        execute_body = execute_response.json()
        self.assertIn("pointer_id", execute_body)
        self.assertIn("metadata", execute_body)
        run_id = execute_body["metadata"]["execution_run_id"]

        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        run_body = run_response.json()
        self.assertEqual(run_body["run_id"], run_id)
        self.assertEqual(run_body["status"], "succeeded")
        self.assertEqual(run_body["summary"]["total_steps"], 1)
        self.assertGreater(run_body["trace_event_count"], 0)

        pointer_id = execute_body["pointer_id"]
        pointer_response = requests.get(
            f"{self.server.base_url}/v1/eap/pointers/{pointer_id}/summary",
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        self.assertEqual(pointer_response.status_code, 200)
        pointer_body = pointer_response.json()
        self.assertEqual(pointer_body["pointer"]["pointer_id"], pointer_id)
        self.assertIn("summary", pointer_body["pointer"])
        self.assertIn("metadata", pointer_body["pointer"])

    def test_execute_macro_rejects_missing_auth(self) -> None:
        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            json={"macro": {"steps": []}},
            timeout=5,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error_type"], "unauthorized")

    def test_execute_macro_rejects_invalid_payload(self) -> None:
        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
            json={"macro": {"steps": [{"tool_name": "echo_text", "arguments": {"text": "hello"}}]}},
            timeout=5,
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["error_type"], "validation_error")
        self.assertIn("Invalid macro payload", body["message"])


if __name__ == "__main__":
    unittest.main()
