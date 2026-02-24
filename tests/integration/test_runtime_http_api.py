import os
import threading
import tempfile
import time
import unittest

import requests

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer
from eap.runtime.policy_profiles import build_scoped_token_policies


def echo_text(text: str) -> str:
    return f"echo:{text}"


def slow_echo(text: str, delay_seconds: float = 0.6) -> str:
    time.sleep(delay_seconds)
    return f"slow:{text}"


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

SLOW_ECHO_SCHEMA = {
    "name": "slow_echo",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "delay_seconds": {"type": "number"},
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

    def test_resume_run_with_approval_decision(self) -> None:
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
                            "approval": {"required": True},
                        }
                    ]
                }
            },
            timeout=5,
        )
        self.assertEqual(execute_response.status_code, 200)
        run_id = execute_response.json()["metadata"]["execution_run_id"]

        resume_response = requests.post(
            f"{self.server.base_url}/v1/eap/runs/{run_id}/resume",
            headers={"Authorization": "Bearer secret-token"},
            json={"approvals": {"step_1": {"decision": "approve"}}},
            timeout=5,
        )
        self.assertEqual(resume_response.status_code, 200)
        resume_body = resume_response.json()
        self.assertEqual(resume_body["run_id"], run_id)
        self.assertTrue(resume_body["metadata"]["resumed_from_checkpoint"])

        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer secret-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["status"], "succeeded")


class RuntimeHttpApiScopedAuthIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-runtime-scoped-auth-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            scoped_bearer_tokens={
                "alice-exec-token": {
                    "actor_id": "alice",
                    "scopes": ["runs:execute", "runs:resume", "runs:read", "pointers:read"],
                },
                "bob-read-token": {
                    "actor_id": "bob",
                    "scopes": ["runs:read", "pointers:read"],
                },
                "charlie-resume-token": {
                    "actor_id": "charlie",
                    "scopes": ["runs:resume"],
                },
                "ops-admin-token": {
                    "actor_id": "ops-admin",
                    "scopes": [
                        "runs:read",
                        "runs:resume",
                        "pointers:read",
                        "runs:read:any",
                        "runs:resume:any",
                        "pointers:read:any",
                    ],
                },
            },
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _execute(self, token: str, *, approval_required: bool = False) -> requests.Response:
        step = {
            "step_id": "step_1",
            "tool_name": "echo_text",
            "arguments": {"text": "hello"},
        }
        if approval_required:
            step["approval"] = {"required": True}
        return requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": f"Bearer {token}"},
            json={"macro": {"steps": [step]}},
            timeout=5,
        )

    def test_scoped_auth_rejects_missing_execute_scope(self) -> None:
        response = self._execute("bob-read-token")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error_type"], "forbidden")

    def test_scoped_auth_enforces_run_and_pointer_ownership(self) -> None:
        execute_response = self._execute("alice-exec-token")
        self.assertEqual(execute_response.status_code, 200)
        body = execute_response.json()
        run_id = body["metadata"]["execution_run_id"]
        pointer_id = body["pointer_id"]

        bob_run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer bob-read-token"},
            timeout=5,
        )
        self.assertEqual(bob_run_response.status_code, 403)
        self.assertEqual(bob_run_response.json()["error_type"], "forbidden")

        admin_run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer ops-admin-token"},
            timeout=5,
        )
        self.assertEqual(admin_run_response.status_code, 200)
        run_body = admin_run_response.json()
        self.assertEqual(run_body["actor_metadata"]["owner_actor_id"], "alice")
        self.assertGreater(run_body["trace_event_count"], 0)
        self.assertEqual(run_body["trace_events"][0]["actor_id"], "alice")

        bob_pointer_response = requests.get(
            f"{self.server.base_url}/v1/eap/pointers/{pointer_id}/summary",
            headers={"Authorization": "Bearer bob-read-token"},
            timeout=5,
        )
        self.assertEqual(bob_pointer_response.status_code, 403)
        self.assertEqual(bob_pointer_response.json()["error_type"], "forbidden")

        admin_pointer_response = requests.get(
            f"{self.server.base_url}/v1/eap/pointers/{pointer_id}/summary",
            headers={"Authorization": "Bearer ops-admin-token"},
            timeout=5,
        )
        self.assertEqual(admin_pointer_response.status_code, 200)

    def test_scoped_auth_enforces_resume_ownership_unless_any_scope(self) -> None:
        execute_response = self._execute("alice-exec-token", approval_required=True)
        self.assertEqual(execute_response.status_code, 200)
        run_id = execute_response.json()["metadata"]["execution_run_id"]

        unauthorized_resume = requests.post(
            f"{self.server.base_url}/v1/eap/runs/{run_id}/resume",
            headers={"Authorization": "Bearer charlie-resume-token"},
            json={"approvals": {"step_1": {"decision": "approve"}}},
            timeout=5,
        )
        self.assertEqual(unauthorized_resume.status_code, 403)
        self.assertEqual(unauthorized_resume.json()["error_type"], "forbidden")

        admin_resume = requests.post(
            f"{self.server.base_url}/v1/eap/runs/{run_id}/resume",
            headers={"Authorization": "Bearer ops-admin-token"},
            json={"approvals": {"step_1": {"decision": "approve"}}},
            timeout=5,
        )
        self.assertEqual(admin_resume.status_code, 200)
        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer ops-admin-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        run_body = run_response.json()
        self.assertEqual(run_body["actor_metadata"]["owner_actor_id"], "alice")
        self.assertEqual(run_body["actor_metadata"]["actor_id"], "ops-admin")
        self.assertEqual(run_body["status"], "succeeded")


class RuntimeHttpApiPolicyProfilesIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-runtime-policy-profiles-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        scoped_tokens, active_profile = build_scoped_token_policies(
            {
                "policy_profile": "strict",
                "tokens": [
                    {"token": "viewer-token", "actor_id": "viewer", "template": "viewer"},
                    {"token": "operator-token", "actor_id": "operator", "template": "operator"},
                    {"token": "auditor-token", "actor_id": "auditor", "template": "auditor"},
                    {"token": "admin-token", "actor_id": "admin", "template": "admin"},
                ],
            }
        )
        self.assertEqual(active_profile, "strict")
        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            scoped_bearer_tokens=scoped_tokens,
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_strict_profile_denies_execute_for_viewer_template(self) -> None:
        response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer viewer-token"},
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
        self.assertEqual(response.json()["error_type"], "forbidden")

    def test_strict_profile_denies_cross_run_resume_for_admin_template(self) -> None:
        execute_response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer operator-token"},
            json={
                "macro": {
                    "steps": [
                        {
                            "step_id": "step_1",
                            "tool_name": "echo_text",
                            "arguments": {"text": "hello"},
                            "approval": {"required": True},
                        }
                    ]
                }
            },
            timeout=5,
        )
        self.assertEqual(execute_response.status_code, 200)
        run_id = execute_response.json()["metadata"]["execution_run_id"]

        resume_response = requests.post(
            f"{self.server.base_url}/v1/eap/runs/{run_id}/resume",
            headers={"Authorization": "Bearer admin-token"},
            json={"approvals": {"step_1": {"decision": "approve"}}},
            timeout=5,
        )
        self.assertEqual(resume_response.status_code, 403)
        self.assertEqual(resume_response.json()["error_type"], "forbidden")

    def test_strict_profile_auditor_can_read_cross_run_summary(self) -> None:
        execute_response = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer operator-token"},
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
        run_id = execute_response.json()["metadata"]["execution_run_id"]

        run_response = requests.get(
            f"{self.server.base_url}/v1/eap/runs/{run_id}",
            headers={"Authorization": "Bearer auditor-token"},
            timeout=5,
        )
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["actor_metadata"]["owner_actor_id"], "operator")


class RuntimeHttpApiRateLimitIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-runtime-rate-limit-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("echo_text", echo_text, ECHO_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="secret-token",
            rate_limit_rules={
                "macro_execute": {"max_requests": 1, "window_seconds": 60},
                "run_resume": {"max_requests": 5, "window_seconds": 60},
                "run_read": {"max_requests": 5, "window_seconds": 60},
                "pointer_summary": {"max_requests": 5, "window_seconds": 60},
            },
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_macro_execute_is_rate_limited_with_retry_after(self) -> None:
        payload = {
            "macro": {
                "steps": [
                    {
                        "step_id": "step_1",
                        "tool_name": "echo_text",
                        "arguments": {"text": "hello"},
                    }
                ]
            }
        }

        first = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
            json=payload,
            timeout=5,
        )
        self.assertEqual(first.status_code, 200)

        second = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
            json=payload,
            timeout=5,
        )
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error_type"], "rate_limited")
        self.assertEqual(second.json()["details"]["operation"], "macro_execute")
        self.assertIn("Retry-After", second.headers)


class RuntimeHttpApiConcurrencyIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-runtime-concurrency-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("slow_echo", slow_echo, SLOW_ECHO_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="secret-token",
            rate_limit_rules={
                "macro_execute": {"max_requests": 20, "window_seconds": 60},
                "run_resume": {"max_requests": 20, "window_seconds": 60},
                "run_read": {"max_requests": 20, "window_seconds": 60},
                "pointer_summary": {"max_requests": 20, "window_seconds": 60},
            },
            concurrency_limits={
                "global_inflight": 1,
                "execute_inflight": 1,
                "resume_inflight": 1,
                "per_run_resume_inflight": 1,
            },
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_execute_is_throttled_when_concurrency_limit_reached(self) -> None:
        payload = {
            "macro": {
                "steps": [
                    {
                        "step_id": "step_1",
                        "tool_name": "slow_echo",
                        "arguments": {"text": "hello", "delay_seconds": 0.7},
                    }
                ]
            }
        }

        first_response: dict = {}

        def _run_first() -> None:
            resp = requests.post(
                f"{self.server.base_url}/v1/eap/macro/execute",
                headers={"Authorization": "Bearer secret-token"},
                json=payload,
                timeout=5,
            )
            first_response["status"] = resp.status_code

        thread = threading.Thread(target=_run_first, daemon=True)
        thread.start()
        time.sleep(0.15)

        second = requests.post(
            f"{self.server.base_url}/v1/eap/macro/execute",
            headers={"Authorization": "Bearer secret-token"},
            json=payload,
            timeout=5,
        )
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["error_type"], "throttled")
        self.assertEqual(second.json()["details"]["operation"], "macro_execute")
        self.assertEqual(second.json()["details"]["limit_type"], "global_inflight")

        thread.join(timeout=5)
        self.assertEqual(first_response.get("status"), 200)


if __name__ == "__main__":
    unittest.main()
