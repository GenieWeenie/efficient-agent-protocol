import unittest

from eap.agent import AgentClient, CompletionRequest, CompletionResponse, LLMProvider


class InterruptedStreamProvider(LLMProvider):
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(text="Hello world")

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(text='{"steps": []}')

    def stream(self, request: CompletionRequest):
        yield "Hel"
        raise RuntimeError("stream interrupted")


class NoStreamProvider(LLMProvider):
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(text="fallback only")

    def complete_with_tools(self, request: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(text='{"steps": []}')

    def stream(self, request: CompletionRequest):
        raise NotImplementedError("stream unsupported")


class StreamingFallbackIntegrationTest(unittest.TestCase):
    def test_stream_interruption_falls_back_to_non_stream(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
            provider=InterruptedStreamProvider(),
        )
        seen = []
        final = client.stream_chat("hello", on_token=seen.append)
        self.assertEqual(final, "Hello world")
        self.assertEqual("".join(seen), "Hello world")

    def test_no_stream_provider_falls_back(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
            provider=NoStreamProvider(),
        )
        final = client.stream_chat("hello")
        self.assertEqual(final, "fallback only")

    def test_fallback_can_be_disabled(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
            provider=NoStreamProvider(),
        )
        with self.assertRaises(NotImplementedError):
            client.stream_chat("hello", fallback_to_non_stream=False)


if __name__ == "__main__":
    unittest.main()
