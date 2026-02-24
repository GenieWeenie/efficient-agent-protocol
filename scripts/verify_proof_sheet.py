#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_ALLOWED_COMMAND_PATH_PREFIXES = (
    "tests/",
    "scripts/",
    "integrations/",
    "docs/",
    "environment/",
    ".github/",
)

_ALLOWED_EVIDENCE_PATH_PREFIXES = (
    "tests/",
    "scripts/",
    "integrations/",
    "docs/",
    "environment/",
    "protocol/",
    "agent/",
    "eap/",
    "sdk/",
    "starter_packs/",
    ".github/",
)


@dataclass
class VerificationResult:
    checked_evidence_paths: list[str]
    checked_command_paths: list[str]
    missing_evidence_paths: list[str]
    missing_command_paths: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing_evidence_paths and not self.missing_command_paths


def _extract_section(markdown: str, heading: str) -> str:
    lines = markdown.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start_index = index + 1
            break
    if start_index is None:
        return ""

    section_lines: list[str] = []
    for line in lines[start_index:]:
        if line.startswith("## "):
            break
        section_lines.append(line)
    return "\n".join(section_lines)


def _extract_backticked_tokens(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)


def _looks_like_repo_path(token: str) -> bool:
    if not token or " " in token:
        return False
    if token.startswith("http://") or token.startswith("https://"):
        return False
    if token.startswith("/"):
        return False
    if token.startswith("POST "):
        return False

    if token == "app.py":
        return True

    if token.startswith(_ALLOWED_EVIDENCE_PATH_PREFIXES):
        return True

    return False


def _extract_bash_blocks(markdown: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", markdown, flags=re.DOTALL)


def _extract_command_paths(markdown: str) -> list[str]:
    blocks = _extract_bash_blocks(markdown)
    candidates: set[str] = set()
    path_pattern = re.compile(r"([A-Za-z0-9_.\-/]+)")

    for block in blocks:
        for token in path_pattern.findall(block):
            if token == "app.py":
                candidates.add(token)
                continue

            normalized = token.rstrip("\\")
            if normalized.startswith(_ALLOWED_COMMAND_PATH_PREFIXES):
                candidates.add(normalized)

    return sorted(candidates)


def verify_proof_sheet(proof_sheet_path: Path, repo_root: Path) -> VerificationResult:
    markdown = proof_sheet_path.read_text(encoding="utf-8")
    capability_table = _extract_section(markdown, "## Side-by-Side Capability Table")

    evidence_tokens = _extract_backticked_tokens(capability_table)
    evidence_paths = sorted({token for token in evidence_tokens if _looks_like_repo_path(token)})

    command_paths = _extract_command_paths(markdown)

    missing_evidence_paths = [
        path for path in evidence_paths if not (repo_root / path).exists()
    ]
    missing_command_paths = [
        path for path in command_paths if not (repo_root / path).exists()
    ]

    if not evidence_paths:
        missing_evidence_paths.append("<no-evidence-paths-found>")
    if not command_paths:
        missing_command_paths.append("<no-command-paths-found>")

    return VerificationResult(
        checked_evidence_paths=evidence_paths,
        checked_command_paths=command_paths,
        missing_evidence_paths=missing_evidence_paths,
        missing_command_paths=missing_command_paths,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/eap_proof_sheet.md evidence and command references."
    )
    parser.add_argument(
        "--proof-sheet",
        default=str(REPO_ROOT / "docs" / "eap_proof_sheet.md"),
        help="Path to the proof sheet markdown file.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root used to resolve relative paths.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    proof_sheet_path = Path(args.proof_sheet).resolve()
    repo_root = Path(args.repo_root).resolve()

    result = verify_proof_sheet(proof_sheet_path=proof_sheet_path, repo_root=repo_root)

    print(f"Proof sheet: {proof_sheet_path}")
    print(f"Checked evidence paths: {len(result.checked_evidence_paths)}")
    print(f"Checked command paths: {len(result.checked_command_paths)}")

    if result.missing_evidence_paths:
        print("Missing evidence paths:")
        for path in result.missing_evidence_paths:
            print(f"- {path}")

    if result.missing_command_paths:
        print("Missing command paths:")
        for path in result.missing_command_paths:
            print(f"- {path}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
