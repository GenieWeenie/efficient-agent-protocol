import os
import unittest
from unittest import mock

from eap.protocol.settings import load_settings


class SettingsTest(unittest.TestCase):
    def test_defaults_load(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
            self.assertEqual(settings.architect.base_url, "http://localhost:1234")
            self.assertEqual(settings.auditor.base_url, "http://localhost:1234")
            self.assertEqual(settings.architect.openai_api_mode, "chat_completions")
            self.assertEqual(settings.auditor.openai_api_mode, "chat_completions")
            self.assertEqual(settings.architect.extra_headers, {})
            self.assertEqual(settings.auditor.extra_headers, {})
            self.assertEqual(settings.executor.max_global_concurrency, 8)
            self.assertEqual(settings.executor.per_tool_limits, {})

    def test_role_specific_overrides(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "EAP_ARCHITECT_MODEL": "arch-model",
                "EAP_AUDITOR_MODEL": "audit-model",
                "EAP_EXTRA_HEADERS_JSON": '{"x-shared":"one","x-role":"global"}',
                "EAP_ARCHITECT_EXTRA_HEADERS_JSON": '{"x-role":"architect"}',
                "EAP_OPENAI_API_MODE": "responses",
                "EAP_AUDITOR_OPENAI_API_MODE": "chat_completions",
            },
            clear=True,
        ):
            settings = load_settings()
            self.assertEqual(settings.architect.model_name, "arch-model")
            self.assertEqual(settings.auditor.model_name, "audit-model")
            self.assertEqual(settings.architect.openai_api_mode, "responses")
            self.assertEqual(settings.auditor.openai_api_mode, "chat_completions")
            self.assertEqual(settings.architect.extra_headers["x-shared"], "one")
            self.assertEqual(settings.architect.extra_headers["x-role"], "architect")
            self.assertEqual(settings.auditor.extra_headers["x-role"], "global")

    def test_invalid_base_url_fails_fast(self) -> None:
        with mock.patch.dict(os.environ, {"EAP_BASE_URL": "localhost:1234"}, clear=True):
            with self.assertRaises(ValueError):
                load_settings()

    def test_executor_global_limit_validation(self) -> None:
        with mock.patch.dict(os.environ, {"EAP_EXECUTOR_MAX_CONCURRENCY": "0"}, clear=True):
            with self.assertRaises(ValueError):
                load_settings()

    def test_executor_per_tool_limit_validation(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "EAP_EXECUTOR_PER_TOOL_LIMITS_JSON": '{"tool_a":{"max_concurrency":2,"requests_per_second":5.0,"burst_capacity":3}}'
            },
            clear=True,
        ):
            settings = load_settings()
            self.assertEqual(settings.executor.per_tool_limits["tool_a"].max_concurrency, 2)
            self.assertEqual(settings.executor.per_tool_limits["tool_a"].requests_per_second, 5.0)

    def test_invalid_extra_headers_validation(self) -> None:
        with mock.patch.dict(os.environ, {"EAP_EXTRA_HEADERS_JSON": '["bad"]'}, clear=True):
            with self.assertRaises(ValueError):
                load_settings()

        with mock.patch.dict(os.environ, {"EAP_AUDITOR_EXTRA_HEADERS_JSON": '{"x-one": 1}'}, clear=True):
            with self.assertRaises(ValueError):
                load_settings()

    def test_invalid_openai_api_mode_validation(self) -> None:
        with mock.patch.dict(os.environ, {"EAP_OPENAI_API_MODE": "legacy"}, clear=True):
            with self.assertRaises(ValueError):
                load_settings()


if __name__ == "__main__":
    unittest.main()
