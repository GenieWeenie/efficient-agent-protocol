import json
import unittest
from unittest.mock import MagicMock, patch

from eap.agent import CompletionRequest, ProviderMessage
from agent.providers.ollama_provider import OllamaProvider


class OllamaProviderTest(unittest.TestCase):
    def _make_provider(self, **kwargs):
        defaults = {"base_url": "http://localhost:11434", "timeout_seconds": 30}
        defaults.update(kwargs)
        return OllamaProvider(**defaults)

    def _make_request(self, content="hello"):
        return CompletionRequest(
            model="llama3",
            messages=[ProviderMessage(role="user", content=content)],
            temperature=0.5,
        )

    def test_complete_returns_response(self) -> None:
        provider = self._make_provider()
        request = self._make_request()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "ollama-ok"}, "done": True}
        mock_resp.raise_for_status.return_value = None
        with patch("agent.providers.ollama_provider.requests.post", return_value=mock_resp) as post:
            response = provider.complete(request)

        self.assertEqual(response.text, "ollama-ok")
        call_kwargs = post.call_args.kwargs
        self.assertEqual(call_kwargs["json"]["model"], "llama3")
        self.assertFalse(call_kwargs["json"]["stream"])
        self.assertIn("/api/chat", post.call_args.args[0])

    def test_complete_with_tools_delegates_to_complete(self) -> None:
        provider = self._make_provider()
        request = self._make_request()

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": "tools-ok"}, "done": True}
        mock_resp.raise_for_status.return_value = None
        with patch("agent.providers.ollama_provider.requests.post", return_value=mock_resp):
            response = provider.complete_with_tools(request)

        self.assertEqual(response.text, "tools-ok")

    def test_stream_yields_tokens(self) -> None:
        provider = self._make_provider()
        request = self._make_request()

        lines = [
            json.dumps({"message": {"content": "Hello"}, "done": False}).encode(),
            json.dumps({"message": {"content": " world"}, "done": False}).encode(),
            json.dumps({"message": {"content": ""}, "done": True}).encode(),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_lines.return_value = iter(lines)
        with patch("agent.providers.ollama_provider.requests.post", return_value=mock_resp):
            tokens = list(provider.stream(request))

        self.assertEqual(tokens, ["Hello", " world"])

    def test_stream_handles_invalid_json(self) -> None:
        provider = self._make_provider()
        request = self._make_request()

        lines = [
            b"not-json",
            json.dumps({"message": {"content": "ok"}, "done": True}).encode(),
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_lines.return_value = iter(lines)
        with patch("agent.providers.ollama_provider.requests.post", return_value=mock_resp):
            tokens = list(provider.stream(request))

        self.assertEqual(tokens, ["ok"])

    def test_headers_include_content_type_and_extra(self) -> None:
        provider = self._make_provider(extra_headers={"X-Custom": "val"})
        headers = provider._headers()
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["X-Custom"], "val")

    def test_base_url_strips_trailing_slash(self) -> None:
        provider = self._make_provider(base_url="http://host:11434/")
        self.assertEqual(provider.base_url, "http://host:11434")

    def test_build_messages_format(self) -> None:
        provider = self._make_provider()
        request = CompletionRequest(
            model="llama3",
            messages=[
                ProviderMessage(role="system", content="be helpful"),
                ProviderMessage(role="user", content="hi"),
            ],
            temperature=0.0,
        )
        msgs = provider._build_messages(request)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0], {"role": "system", "content": "be helpful"})
        self.assertEqual(msgs[1], {"role": "user", "content": "hi"})


if __name__ == "__main__":
    unittest.main()
