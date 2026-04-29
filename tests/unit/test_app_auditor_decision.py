"""Regression tests for the app.py auditor decision parser (Phase-14 R8).

Previously, ``app.py`` approved any LLM response that contained the literal
substring ``APPROVED`` — a malicious or noisy auditor saying "I will never
approve this..." would fall through to execution. The new parser requires a
structured JSON ``{"decision": "approve" | "reject", "reason": "..."}``
response and defaults to ``reject`` for any unparseable / unknown payload.

``app.py`` is a Streamlit module that imports ``streamlit`` at module load
and immediately calls ``st.set_page_config``. To avoid pulling Streamlit
into the unit-test environment, we extract just the
``parse_auditor_decision`` function (and its private constants) out of the
source via ``ast`` and exec it in an isolated namespace.
"""

from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path


def _extract_parse_auditor_decision():
    """Pull the parse_auditor_decision function out of app.py without import."""
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    namespace: dict[str, object] = {"json": json, "re": re}
    captured = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_AUDITOR_REJECT_REASON_FALLBACK"
            for t in node.targets
        ):
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<app_extract>", "exec"), namespace)  # noqa: S102
        if isinstance(node, ast.FunctionDef) and node.name == "parse_auditor_decision":
            exec(compile(ast.Module(body=[node], type_ignores=[]), "<app_extract>", "exec"), namespace)  # noqa: S102
            captured = True
            break
    if not captured:
        raise RuntimeError("parse_auditor_decision not found in app.py")
    return namespace["parse_auditor_decision"]


parse_auditor_decision = _extract_parse_auditor_decision()


class AuditorDecisionParserTest(unittest.TestCase):
    def test_parses_clean_approve_payload(self) -> None:
        decision, reason = parse_auditor_decision(
            '{"decision": "approve", "reason": "Looks safe"}'
        )
        self.assertEqual(decision, "approve")
        self.assertIn("safe", reason.lower())

    def test_parses_clean_reject_payload(self) -> None:
        decision, reason = parse_auditor_decision(
            '{"decision": "reject", "reason": "Calls dangerous tool"}'
        )
        self.assertEqual(decision, "reject")
        self.assertIn("dangerous", reason)

    def test_substring_approval_no_longer_executes(self) -> None:
        """The old ``APPROVED in upper()`` path is gone.

        A malicious response containing the literal word ``APPROVED`` but no
        structured decision must be treated as a reject.
        """
        decision, reason = parse_auditor_decision("APPROVED — but only kidding")
        self.assertEqual(decision, "reject")
        self.assertTrue(reason)

    def test_extracts_json_from_surrounding_prose(self) -> None:
        decision, _reason = parse_auditor_decision(
            "Here is my review:\n```json\n"
            '{"decision": "reject", "reason": "Bad"}\n```'
        )
        self.assertEqual(decision, "reject")

    def test_unknown_decision_value_rejects(self) -> None:
        decision, _reason = parse_auditor_decision(
            '{"decision": "maybe", "reason": "uncertain"}'
        )
        self.assertEqual(decision, "reject")

    def test_empty_response_rejects(self) -> None:
        decision, _reason = parse_auditor_decision("")
        self.assertEqual(decision, "reject")

    def test_non_string_response_rejects(self) -> None:
        decision, _reason = parse_auditor_decision(None)
        self.assertEqual(decision, "reject")


if __name__ == "__main__":
    unittest.main()
