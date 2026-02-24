import unittest
from unittest.mock import MagicMock, patch

from eap.agent import (
    AnthropicProvider,
    CompletionRequest,
    GoogleProvider,
    OpenAIProvider,
    ProviderMessage,
)


class ProviderAdaptersTest(unittest.TestCase):
    def test_openai_provider_normalizes_response(self) -> None:
        provider = OpenAIProvider(
            endpoint="http://localhost:1234/v1/chat/completions",
            api_key="secret",
            timeout_seconds=10,
        )
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[ProviderMessage(role="user", content="hello")],
            temperature=0.1,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "openai-ok"}}]}
        mock_response.raise_for_status.return_value = None
        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response) as post:
            response = provider.complete(request)

        self.assertEqual(response.text, "openai-ok")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "gpt-4o-mini")

    def test_openai_provider_stream_parses_sse_chunks(self) -> None:
        provider = OpenAIProvider(
            endpoint="http://localhost:1234/v1/chat/completions",
            api_key="secret",
            timeout_seconds=10,
        )
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[ProviderMessage(role="user", content="hello")],
            temperature=0.1,
        )

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.iter_lines.return_value = [
            b'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            b'data: {"choices":[{"delta":{"content":"lo"}}]}',
            b"data: [DONE]",
        ]
        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response) as post:
            chunks = list(provider.stream(request))

        self.assertEqual(chunks, ["Hel", "lo"])
        kwargs = post.call_args.kwargs
        self.assertTrue(kwargs["stream"])
        self.assertTrue(kwargs["json"]["stream"])

    def test_openai_provider_includes_configured_extra_headers(self) -> None:
        provider = OpenAIProvider(
            endpoint="http://localhost:1234/v1/chat/completions",
            api_key="secret",
            timeout_seconds=10,
            extra_headers={"x-openclaw-agent-id": "router-123"},
        )
        request = CompletionRequest(
            model="gpt-4o-mini",
            messages=[ProviderMessage(role="user", content="hello")],
            temperature=0.1,
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status.return_value = None

        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response) as post:
            provider.complete(request)

        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["x-openclaw-agent-id"], "router-123")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")

    def test_anthropic_provider_normalizes_response(self) -> None:
        provider = AnthropicProvider(
            endpoint="https://api.anthropic.com/v1/messages",
            api_key="anthro-key",
            timeout_seconds=15,
        )
        request = CompletionRequest(
            model="claude-3-5-sonnet-latest",
            messages=[
                ProviderMessage(role="system", content="system prompt"),
                ProviderMessage(role="user", content="hello"),
            ],
            temperature=0.2,
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [{"type": "text", "text": "anthropic-ok"}]}
        mock_response.raise_for_status.return_value = None
        with patch("agent.providers.anthropic_provider.requests.post", return_value=mock_response) as post:
            response = provider.complete(request)

        self.assertEqual(response.text, "anthropic-ok")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["x-api-key"], "anthro-key")
        self.assertIn("system", kwargs["json"])

    def test_google_provider_normalizes_response_and_tools(self) -> None:
        provider = GoogleProvider(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            api_key="google-key",
            timeout_seconds=20,
        )
        request = CompletionRequest(
            model="gemini-1.5-pro",
            messages=[
                ProviderMessage(role="system", content="system prompt"),
                ProviderMessage(role="user", content="hello"),
            ],
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "fetch_data",
                        "description": "Fetch data",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "google-ok"}]}}]
        }
        mock_response.raise_for_status.return_value = None
        with patch("agent.providers.google_provider.requests.post", return_value=mock_response) as post:
            response = provider.complete_with_tools(request)

        self.assertEqual(response.text, "google-ok")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["params"]["key"], "google-key")
        self.assertIn("tools", kwargs["json"])
        declarations = kwargs["json"]["tools"][0]["functionDeclarations"]
        self.assertEqual(declarations[0]["name"], "fetch_data")


if __name__ == "__main__":
    unittest.main()
