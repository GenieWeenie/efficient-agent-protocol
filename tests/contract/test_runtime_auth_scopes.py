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


class RuntimeAuthFailClosedContractTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-auth-fail-closed-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        self.executor = AsyncLocalExecutor(self.state_manager, registry)

    def tearDown(self) -> None:
        if hasattr(self, "server"):
            self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_runtime_auth_fails_closed_without_config(self) -> None:
        self.server = EAPRuntimeHTTPServer(
            executor=self.executor,
            state_manager=self.state_manager,
        ).start()
        time.sleep(0.05)

        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
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
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error_type"], "unauthorized")

    def test_local_dev_auth_escape_hatch_is_explicit_and_marked(self) -> None:
        self.server = EAPRuntimeHTTPServer(
            executor=self.executor,
            state_manager=self.state_manager,
            allow_unauthenticated_local_dev=True,
        ).start()
        time.sleep(0.05)

        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
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
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["metadata"]["execution_run_id"]

        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        actor_metadata = run_response.json()["actor_metadata"]
        self.assertEqual(actor_metadata["actor_id"], "local-dev-anonymous")
        self.assertEqual(actor_metadata["auth_subject"], "unauthenticated_local_dev")
        self.assertEqual(actor_metadata["policy_profile"], "local_dev")
        self.assertTrue(actor_metadata["local_dev_auth"])

    def test_local_dev_auth_escape_hatch_rejects_remote_bind(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a loopback host"):
            EAPRuntimeHTTPServer(
                executor=self.executor,
                state_manager=self.state_manager,
                host="0.0.0.0",
                allow_unauthenticated_local_dev=True,
            )


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
