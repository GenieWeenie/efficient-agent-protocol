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
            self.assertEqual(settings.executor.max_global_concurrency, 8)
            self.assertEqual(settings.executor.per_tool_limits, {})

    def test_role_specific_overrides(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "EAP_ARCHITECT_MODEL": "arch-model",
                "EAP_AUDITOR_MODEL": "audit-model",
            },
            clear=True,
        ):
            settings = load_settings()
            self.assertEqual(settings.architect.model_name, "arch-model")
            self.assertEqual(settings.auditor.model_name, "audit-model")

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


if __name__ == "__main__":
    unittest.main()
