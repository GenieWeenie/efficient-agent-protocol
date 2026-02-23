import unittest

import eap.agent as eap_agent
import eap.environment as eap_environment
import eap.protocol as eap_protocol


class PublicApiContractTest(unittest.TestCase):
    def test_eap_protocol_exports_are_stable(self) -> None:
        expected = {
            "PointerResponse",
            "PersistedWorkflowGraph",
            "ToolErrorPayload",
            "ToolCall",
            "BranchingRule",
            "RetryPolicy",
            "MemoryStrategy",
            "ConversationSession",
            "ConversationTurn",
            "ExecutionTraceEventType",
            "ExecutionTraceEvent",
            "ToolExecutionLimit",
            "ExecutionLimits",
            "BatchedMacroRequest",
            "WorkflowEdgeKind",
            "WorkflowGraphEdge",
            "WorkflowGraphNode",
            "StateManager",
            "configure_logging",
            "LLMClientSettings",
            "ToolLimitSettings",
            "ExecutorLimitSettings",
            "EAPSettings",
            "load_settings",
            "PointerStoreBackend",
            "PostgresPointerStore",
            "RedisPointerStore",
            "SQLitePointerStore",
        }
        actual = set(eap_protocol.__all__)
        self.assertSetEqual(actual, expected)
        for symbol in actual:
            self.assertTrue(hasattr(eap_protocol, symbol), f"eap.protocol missing export: {symbol}")

    def test_eap_environment_exports_are_stable(self) -> None:
        expected = {
            "AsyncLocalExecutor",
            "DistributedCoordinator",
            "ToolRegistry",
            "ToolDefinition",
            "InputValidationError",
            "PluginManifestError",
            "PluginLoadError",
            "DEFAULT_PLUGIN_ENTRYPOINT_GROUP",
            "discover_plugin_entry_points",
            "load_plugins_into_registry",
        }
        actual = set(eap_environment.__all__)
        self.assertSetEqual(actual, expected)
        for symbol in actual:
            self.assertTrue(hasattr(eap_environment, symbol), f"eap.environment missing export: {symbol}")

    def test_eap_agent_exports_are_stable(self) -> None:
        expected = {
            "MacroCompiler",
            "WorkflowGraphCompiler",
            "AgentClient",
            "ProviderMessage",
            "CompletionRequest",
            "CompletionResponse",
            "LLMProvider",
            "OpenAIProvider",
            "AnthropicProvider",
            "GoogleProvider",
            "create_provider",
        }
        actual = set(eap_agent.__all__)
        self.assertSetEqual(actual, expected)
        for symbol in actual:
            self.assertTrue(hasattr(eap_agent, symbol), f"eap.agent missing export: {symbol}")


if __name__ == "__main__":
    unittest.main()
