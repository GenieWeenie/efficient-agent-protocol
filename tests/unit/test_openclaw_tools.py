import json
import unittest
from unittest.mock import patch

from eap.environment.openclaw_client import (
    OpenClawToolInvokeError,
    OpenClawToolInvokeResponse,
)
from eap.environment.tools.openclaw_tools import invoke_openclaw_tool


class OpenClawToolsUnitTest(unittest.TestCase):
    def test_invoke_openclaw_tool_returns_json_payload(self) -> None:
        response = OpenClawToolInvokeResponse(
            status_code=200,
            payload={"ok": True, "result": {"answer": 42}},
        )
        with patch("environment.tools.openclaw_tools.invoke_openclaw_tools_api", return_value=response):
            raw = invoke_openclaw_tool(
                base_url="https://gateway.openclaw.local",
                api_key="secret-token",
                tool_name="echo_tool",
                tool_arguments={"x": 1},
            )
        parsed = json.loads(raw)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["result"]["answer"], 42)

    def test_invoke_openclaw_tool_translates_client_error(self) -> None:
        with patch(
            "environment.tools.openclaw_tools.invoke_openclaw_tools_api",
            side_effect=OpenClawToolInvokeError(
                message="Tool denied by policy.",
                status_code=403,
                error_type="policy_denied",
            ),
        ):
            with self.assertRaises(RuntimeError) as context:
                invoke_openclaw_tool(
                    base_url="https://gateway.openclaw.local",
                    api_key="secret-token",
                    tool_name="blocked_tool",
                )

        self.assertIn("policy_denied", str(context.exception))
        self.assertIn("status=403", str(context.exception))


if __name__ == "__main__":
    unittest.main()
