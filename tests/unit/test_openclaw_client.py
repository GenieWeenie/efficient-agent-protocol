import unittest
from unittest.mock import patch

from eap.environment.openclaw_client import (
    OpenClawToolInvokeError,
    OpenClawToolInvokeRequest,
    invoke_openclaw_tools_api,
)


class _MockResponse:
    def __init__(self, status_code, payload, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class OpenClawClientUnitTest(unittest.TestCase):
    def test_invoke_openclaw_tools_api_success(self) -> None:
        mock_response = _MockResponse(
            status_code=200,
            payload={"ok": True, "tool": "echo_tool", "result": {"text": "hello"}},
        )
        with patch("environment.openclaw_client.requests.post", return_value=mock_response) as post:
            result = invoke_openclaw_tools_api(
                base_url="https://gateway.openclaw.local",
                api_key="secret-token",
                request=OpenClawToolInvokeRequest(name="echo_tool", arguments={"text": "hello"}),
                timeout_seconds=12,
                account_id="acct-123",
                channel_id="chan-456",
            )

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.payload["ok"])
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["json"]["name"], "echo_tool")
        self.assertEqual(kwargs["json"]["arguments"]["text"], "hello")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(kwargs["headers"]["x-openclaw-account-id"], "acct-123")
        self.assertEqual(kwargs["headers"]["x-openclaw-channel-id"], "chan-456")

    def test_invoke_openclaw_tools_api_maps_unauthorized(self) -> None:
        mock_response = _MockResponse(
            status_code=401,
            payload={"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid bearer token."}},
        )
        with patch("environment.openclaw_client.requests.post", return_value=mock_response):
            with self.assertRaises(OpenClawToolInvokeError) as context:
                invoke_openclaw_tools_api(
                    base_url="https://gateway.openclaw.local",
                    api_key="wrong-token",
                    request=OpenClawToolInvokeRequest(name="echo_tool", arguments={}),
                )

        error = context.exception
        self.assertEqual(error.error_type, "unauthorized")
        self.assertEqual(error.status_code, 401)
        self.assertIn("invalid bearer token", str(error).lower())

    def test_invoke_openclaw_tools_api_maps_policy_denied(self) -> None:
        mock_response = _MockResponse(
            status_code=403,
            payload={
                "error": {
                    "code": "TOOL_INVOKE_POLICY_DENIED",
                    "message": "Tool denied by policy.",
                    "details": {"policy": "denylist"},
                }
            },
        )
        with patch("environment.openclaw_client.requests.post", return_value=mock_response):
            with self.assertRaises(OpenClawToolInvokeError) as context:
                invoke_openclaw_tools_api(
                    base_url="https://gateway.openclaw.local",
                    api_key="secret-token",
                    request=OpenClawToolInvokeRequest(name="blocked_tool", arguments={}),
                )

        error = context.exception
        self.assertEqual(error.error_type, "policy_denied")
        self.assertEqual(error.status_code, 403)
        self.assertEqual(error.details["policy"], "denylist")
        self.assertEqual(error.details["code"], "TOOL_INVOKE_POLICY_DENIED")

    def test_invoke_openclaw_tools_api_reads_retry_after(self) -> None:
        mock_response = _MockResponse(
            status_code=429,
            payload={"error": {"code": "RATE_LIMITED", "message": "Too many requests."}},
            headers={"Retry-After": "17"},
        )
        with patch("environment.openclaw_client.requests.post", return_value=mock_response):
            with self.assertRaises(OpenClawToolInvokeError) as context:
                invoke_openclaw_tools_api(
                    base_url="https://gateway.openclaw.local",
                    api_key="secret-token",
                    request=OpenClawToolInvokeRequest(name="echo_tool", arguments={}),
                )

        error = context.exception
        self.assertEqual(error.error_type, "rate_limited")
        self.assertEqual(error.retry_after_seconds, 17)


if __name__ == "__main__":
    unittest.main()
