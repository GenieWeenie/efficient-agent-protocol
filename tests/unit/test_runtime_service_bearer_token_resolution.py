"""Tests for the bearer-token resolution helper in eap_runtime_service.py.

Phase-14 R10: bearer tokens passed via ``--bearer-token`` are visible in
``ps``/``/proc/<pid>/cmdline``. The runtime service now also accepts the
token via the ``EAP_RUNTIME_BEARER_TOKEN`` environment variable or via
``--bearer-token-file`` (a path mounted from a Docker / Kubernetes secret).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


def _load_runtime_service_module():
    repo_root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "eap_runtime_service_module_for_test",
        repo_root / "scripts" / "eap_runtime_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


runtime_service = _load_runtime_service_module()


def _make_args(**kwargs) -> argparse.Namespace:
    defaults = {"bearer_token": "", "bearer_token_file": ""}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class ResolveBearerTokenTest(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure environment is clean for each test.
        self._previous_env = os.environ.pop(runtime_service.BEARER_TOKEN_ENV_VAR, None)

    def tearDown(self) -> None:
        os.environ.pop(runtime_service.BEARER_TOKEN_ENV_VAR, None)
        if self._previous_env is not None:
            os.environ[runtime_service.BEARER_TOKEN_ENV_VAR] = self._previous_env

    def test_resolve_returns_empty_when_nothing_provided(self) -> None:
        token = runtime_service._resolve_bearer_token(_make_args())
        self.assertEqual(token, "")

    def test_resolve_uses_env_var_when_no_flag(self) -> None:
        os.environ[runtime_service.BEARER_TOKEN_ENV_VAR] = "env-token-value"
        token = runtime_service._resolve_bearer_token(_make_args())
        self.assertEqual(token, "env-token-value")

    def test_resolve_prefers_flag_over_env_var(self) -> None:
        os.environ[runtime_service.BEARER_TOKEN_ENV_VAR] = "env-token-value"
        token = runtime_service._resolve_bearer_token(_make_args(bearer_token="flag-token"))
        self.assertEqual(token, "flag-token")

    def test_resolve_reads_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".token", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("file-token-value\n")
            file_path = fh.name
        try:
            token = runtime_service._resolve_bearer_token(
                _make_args(bearer_token_file=file_path)
            )
            self.assertEqual(token, "file-token-value")
        finally:
            os.remove(file_path)

    def test_resolve_rejects_both_flag_and_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".token", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("file-token-value\n")
            file_path = fh.name
        try:
            with self.assertRaises(ValueError):
                runtime_service._resolve_bearer_token(
                    _make_args(bearer_token="flag-token", bearer_token_file=file_path)
                )
        finally:
            os.remove(file_path)

    def test_resolve_rejects_empty_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".token", delete=False, encoding="utf-8"
        ) as fh:
            fh.write("")
            file_path = fh.name
        try:
            with self.assertRaises(ValueError):
                runtime_service._resolve_bearer_token(_make_args(bearer_token_file=file_path))
        finally:
            os.remove(file_path)

    def test_resolve_rejects_missing_file(self) -> None:
        with self.assertRaises(ValueError):
            runtime_service._resolve_bearer_token(
                _make_args(bearer_token_file="/nonexistent/path/token.txt")
            )


if __name__ == "__main__":
    unittest.main()
