import unittest

from eap.agent import AgentClient, CompletionRequest, CompletionResponse, LLMProvider


class FakeProvider(LLMProvider):
    def __init__(self) -> None:
        self.complete_calls = []
        self.tool_calls = []

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.complete_calls.append(request)
        return CompletionResponse(text="provider-chat-ok")

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        self.tool_calls.append(request)
        return CompletionResponse(text='{"steps": []}')

    def stream(self, request: CompletionRequest):
        return iter(["A", "B"])


class ProviderAbstractionTest(unittest.TestCase):
    def test_agent_client_uses_injected_provider(self) -> None:
        provider = FakeProvider()
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="test-model",
            provider=provider,
            system_prompt="sys prompt",
        )

        chat_output = client.chat("hello")
        macro_output = client.generate_macro("plan this", {"tool_hash": {"type": "object"}})

        self.assertEqual(chat_output, "provider-chat-ok")
        self.assertEqual(macro_output.steps, [])
        self.assertEqual(len(provider.complete_calls), 1)
        self.assertEqual(len(provider.tool_calls), 1)
        self.assertEqual(provider.complete_calls[0].messages[1].content, "hello")
        self.assertIn("plan this", provider.tool_calls[0].messages[1].content)

    def test_stream_chat_assembles_content_and_invokes_callback(self) -> None:
        provider = FakeProvider()
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="test-model",
            provider=provider,
            system_prompt="sys prompt",
        )
        observed = []
        final_text = client.stream_chat("hello", on_token=observed.append)

        self.assertEqual(final_text, "AB")
        self.assertEqual(observed, ["A", "B"])


if __name__ == "__main__":
    unittest.main()
