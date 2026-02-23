import unittest
from unittest.mock import MagicMock, patch

from eap.agent.agent_client import AgentClient


class AgentClientTest(unittest.TestCase):
    def test_chat_uses_headers_timeout_and_temperature(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
            api_key="secret",
            temperature=0.3,
            timeout_seconds=12,
            system_prompt="sys",
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status.return_value = None

        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response) as post:
            result = client.chat("hello")

        self.assertEqual(result, "ok")
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 12)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["temperature"], 0.3)

    def test_generate_macro_returns_compiled_model(self) -> None:
        client = AgentClient(base_url="http://localhost:1234", model_name="model-a")
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "{\"steps\": []}"}}]}
        mock_response.raise_for_status.return_value = None

        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response):
            macro = client.generate_macro("do thing", {"x_hash": {"type": "object"}})

        self.assertEqual(macro.steps, [])

    def test_not_needed_api_key_omits_auth_header(self) -> None:
        client = AgentClient(base_url="http://localhost:1234", model_name="model-a", api_key="not-needed")
        self.assertEqual(client._headers(), {})

    def test_generate_macro_injects_memory_context(self) -> None:
        client = AgentClient(base_url="http://localhost:1234", model_name="model-a")
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "{\"steps\": []}"}}]}
        mock_response.raise_for_status.return_value = None

        with patch("agent.providers.openai_provider.requests.post", return_value=mock_response) as post:
            client.generate_macro(
                "follow up",
                {"x_hash": {"type": "object"}},
                memory_context="[user] prior question\n[assistant] prior answer",
            )

        payload = post.call_args.kwargs["json"]
        user_message = payload["messages"][1]["content"]
        self.assertIn("### MEMORY CONTEXT ###", user_message)
        self.assertIn("prior question", user_message)


if __name__ == "__main__":
    unittest.main()
