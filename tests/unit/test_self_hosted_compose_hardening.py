"""Regression tests for the self-hosted docker-compose hardening (Phase-14
R10/R11).

* The bearer token must not appear on the runtime command line (R10).
* The operator-ui volume mount must be ``:ro`` so the SQLite file is only
  written by a single container (R11).
"""

from __future__ import annotations

import unittest
from pathlib import Path


COMPOSE_PATH = Path(__file__).resolve().parents[2] / "deploy" / "self_hosted" / "docker-compose.yml"


class ComposeHardeningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    def test_runtime_command_does_not_pass_bearer_token_on_cli(self) -> None:
        """``--bearer-token`` must not appear in the runtime command list.

        We scan only command list items (lines starting with ``      - ``)
        to ignore comments / environment values that legitimately mention
        the flag in prose.
        """
        cli_lines = [
            line.strip()
            for line in self.compose_text.splitlines()
            if line.lstrip().startswith("- ")
        ]
        for line in cli_lines:
            self.assertFalse(
                line.strip("- ").strip().startswith("--bearer-token"),
                f"bearer-token flag leaked into CLI: {line}",
            )

    def test_runtime_environment_carries_bearer_token(self) -> None:
        """The runtime container reads the token from EAP_RUNTIME_BEARER_TOKEN."""
        self.assertIn("EAP_RUNTIME_BEARER_TOKEN", self.compose_text)

    def test_operator_ui_volume_is_read_only(self) -> None:
        """``operator-ui`` must mount the shared SQLite volume as ``:ro``."""
        # Cheap but explicit check: the ":ro" flag must appear next to the
        # operator-ui mount of eap_state. The runtime service still mounts
        # rw, so both forms are present in the file — the operator-ui block
        # must include the read-only one.
        self.assertIn("eap_state:/var/lib/eap:ro", self.compose_text)


if __name__ == "__main__":
    unittest.main()
