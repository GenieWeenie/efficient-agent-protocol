import unittest

from eap.agent import AgentClient
from eap.agent import AnthropicProvider, GoogleProvider, OpenAIProvider


class ProviderSelectionIntegrationTest(unittest.TestCase):
    def test_default_local_provider_is_openai_compatible(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
        )
        self.assertIsInstance(client.provider, OpenAIProvider)

    def test_anthropic_provider_selected_when_configured(self) -> None:
        client = AgentClient(
            base_url="https://api.anthropic.com",
            model_name="claude-3-5-sonnet-latest",
            api_key="anthropic-key",
            provider_name="anthropic",
        )
        self.assertIsInstance(client.provider, AnthropicProvider)

    def test_google_provider_selected_when_configured(self) -> None:
        client = AgentClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model_name="gemini-1.5-pro",
            api_key="google-key",
            provider_name="google",
        )
        self.assertIsInstance(client.provider, GoogleProvider)

    def test_invalid_provider_fails_fast_without_fallback(self) -> None:
        with self.assertRaises(ValueError):
            AgentClient(
                base_url="http://localhost:1234",
                model_name="model-a",
                provider_name="invalid-provider",
            )

    def test_invalid_provider_uses_fallback_when_configured(self) -> None:
        client = AgentClient(
            base_url="http://localhost:1234",
            model_name="model-a",
            provider_name="invalid-provider",
            fallback_provider_name="local",
        )
        self.assertIsInstance(client.provider, OpenAIProvider)

    def test_missing_api_key_for_anthropic_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            AgentClient(
                base_url="https://api.anthropic.com",
                model_name="claude-3-5-sonnet-latest",
                api_key="not-needed",
                provider_name="anthropic",
            )


if __name__ == "__main__":
    unittest.main()
