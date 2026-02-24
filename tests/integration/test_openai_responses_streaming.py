import unittest
from unittest.mock import MagicMock, patch

from eap.agent import AgentClient


class OpenAIResponsesStreamingIntegrationTest(unittest.TestCase):
    def test_agent_client_stream_chat_uses_responses_streaming(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="gpt-4.1-mini",
            api_key="secret",
            openai_api_mode="responses",
        )
        stream_response = MagicMock()
        stream_response.raise_for_status.return_value = None
        stream_response.iter_lines.return_value = [
            b'data: {"type":"response.output_text.delta","delta":"Hel"}',
            b'data: {"type":"response.output_text.delta","delta":"lo"}',
            b'data: {"type":"response.output_text.done","text":"Hello"}',
            b"data: [DONE]",
        ]

        seen = []
        with patch("agent.providers.openai_provider.requests.post", return_value=stream_response) as post:
            final = client.stream_chat("hello", on_token=seen.append, fallback_to_non_stream=False)

        self.assertEqual(final, "Hello")
        self.assertEqual(seen, ["Hel", "lo"])
        kwargs = post.call_args.kwargs
        self.assertTrue(kwargs["stream"])
        self.assertTrue(kwargs["json"]["stream"])
        self.assertIn("input", kwargs["json"])

    def test_agent_client_stream_chat_falls_back_when_responses_stream_errors(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="gpt-4.1-mini",
            api_key="secret",
            openai_api_mode="responses",
        )
        stream_response = MagicMock()
        stream_response.raise_for_status.return_value = None
        stream_response.iter_lines.return_value = [
            b'data: {"type":"response.error","error":{"code":"policy_denied","message":"Denied by policy"}}'
        ]
        completion_response = MagicMock()
        completion_response.raise_for_status.return_value = None
        completion_response.json.return_value = {"output_text": "fallback-response"}

        seen = []
        with patch(
            "agent.providers.openai_provider.requests.post",
            side_effect=[stream_response, completion_response],
        ) as post:
            final = client.stream_chat("hello", on_token=seen.append)

        self.assertEqual(final, "fallback-response")
        self.assertEqual(seen, ["fallback-response"])
        stream_call_kwargs = post.call_args_list[0].kwargs
        complete_call_kwargs = post.call_args_list[1].kwargs
        self.assertTrue(stream_call_kwargs["stream"])
        self.assertTrue(stream_call_kwargs["json"]["stream"])
        self.assertNotIn("stream", complete_call_kwargs)


if __name__ == "__main__":
    unittest.main()
