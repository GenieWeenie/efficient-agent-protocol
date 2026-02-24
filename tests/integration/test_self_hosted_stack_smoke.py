import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import FETCH_SCHEMA, fetch_user_data
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer


class SelfHostedStackSmokeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-self-hosted-smoke-", suffix=".db")
        os.close(fd)

        self.state_manager = StateManager(db_path=self.db_path)
        registry = ToolRegistry()
        registry.register("fetch_user_data", fetch_user_data, FETCH_SCHEMA)
        executor = AsyncLocalExecutor(self.state_manager, registry)

        self.server = EAPRuntimeHTTPServer(
            executor=executor,
            state_manager=self.state_manager,
            required_bearer_token="self-hosted-test-token",
        ).start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.stop()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_smoke_script_executes_remote_runtime_endpoints(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eap-self-hosted-artifacts-") as temp_dir:
            artifact_path = Path(temp_dir) / "self_hosted_smoke.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/self_hosted_stack_smoke.py",
                    "--base-url",
                    self.server.base_url,
                    "--bearer-token",
                    "self-hosted-test-token",
                    "--artifact-path",
                    str(artifact_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr + completed.stdout)
            self.assertTrue(artifact_path.exists())
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))

            execute_payload = payload.get("execute", {})
            self.assertIn("pointer_id", execute_payload)
            self.assertIn("metadata", execute_payload)
            self.assertEqual(payload.get("run", {}).get("status"), "succeeded")


if __name__ == "__main__":
    unittest.main()
