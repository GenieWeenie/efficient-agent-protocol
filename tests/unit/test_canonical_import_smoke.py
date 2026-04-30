"""Smoke tests for canonical EAP import paths consumed by Cue-Auto (GEN-219).

These verify the upstream-visible import surface that Cue-Auto and other
downstream consumers depend on. Keep these as pure import-only checks so
they run in any environment without optional dependencies.
"""

import importlib
import unittest


class CanonicalProvidersImportSmoke(unittest.TestCase):
    def test_eap_agent_providers_package(self) -> None:
        pkg = importlib.import_module("eap.agent.providers")
        for name in (
            "LLMProvider",
            "CompletionRequest",
            "CompletionResponse",
            "ProviderMessage",
            "create_provider",
        ):
            self.assertTrue(
                hasattr(pkg, name),
                f"eap.agent.providers must expose {name}",
            )

    def test_eap_agent_providers_base_module(self) -> None:
        from eap.agent.providers.base import (
            CompletionRequest,
            CompletionResponse,
            LLMProvider,
            ProviderMessage,
        )

        self.assertTrue(callable(LLMProvider))
        self.assertTrue(callable(CompletionRequest))
        self.assertTrue(callable(CompletionResponse))
        self.assertTrue(callable(ProviderMessage))

    def test_eap_agent_providers_factory_module(self) -> None:
        from eap.agent.providers.factory import create_provider

        self.assertTrue(callable(create_provider))

    def test_legacy_agent_providers_still_resolves(self) -> None:
        # Legacy shim path Cue-Auto historically used must keep working.
        legacy_base = importlib.import_module("agent.providers.base")
        legacy_factory = importlib.import_module("agent.providers.factory")
        self.assertTrue(hasattr(legacy_base, "LLMProvider"))
        self.assertTrue(hasattr(legacy_factory, "create_provider"))


class CanonicalMemoryStrategyImportSmoke(unittest.TestCase):
    def test_memory_strategy_from_eap_protocol_models(self) -> None:
        from eap.protocol.models import MemoryStrategy

        # Sanity-check it is the same enum exported via the package root.
        from eap.protocol import MemoryStrategy as PackageMemoryStrategy

        self.assertIs(MemoryStrategy, PackageMemoryStrategy)
        self.assertTrue(hasattr(MemoryStrategy, "FULL"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
