#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import eap.agent as eap_agent
import eap.environment as eap_environment
import eap.protocol as eap_protocol
from eap.protocol import (
    PersistedWorkflowGraph,
    ToolErrorPayload,
    WorkflowEdgeKind,
    WorkflowGraphEdge,
    WorkflowGraphNode,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK_PATH = REPO_ROOT / "docs" / "v1_contract_lock.json"
DEFAULT_PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
DEFAULT_SETTINGS_PATH = REPO_ROOT / "protocol" / "settings.py"
DEFAULT_TS_CLIENT_PATH = REPO_ROOT / "sdk" / "typescript" / "src" / "client.ts"
DEFAULT_GO_CLIENT_PATH = REPO_ROOT / "sdk" / "go" / "client.go"


def _extract_project_version_from_text(pyproject_text: str) -> str:
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', pyproject_text)
    if not match:
        raise ValueError("Could not find [project].version in pyproject.toml")
    return match.group(1)


def _extract_project_version(pyproject_path: Path) -> str:
    return _extract_project_version_from_text(pyproject_path.read_text(encoding="utf-8"))


def _collect_sdk_http_paths(ts_client_path: Path, go_client_path: Path) -> list[str]:
    ts_client = ts_client_path.read_text(encoding="utf-8")
    go_client = go_client_path.read_text(encoding="utf-8")
    pattern = re.compile(r'"/v1/eap/[^"]+"')
    tokens = set(pattern.findall(ts_client)) | set(pattern.findall(go_client))
    normalized = sorted(token.strip('"') for token in tokens)
    return normalized


def _collect_settings_env_keys(settings_path: Path) -> list[str]:
    text = settings_path.read_text(encoding="utf-8")
    tokens = re.findall(r'os\.getenv\(\s*"([^"]+)"', text)
    keys = {token for token in tokens if token.startswith("EAP_")}
    for prefix in ("EAP_ARCHITECT", "EAP_AUDITOR"):
        for suffix in (
            "BASE_URL",
            "MODEL",
            "API_KEY",
            "TIMEOUT_SECONDS",
            "TEMPERATURE",
            "OPENAI_API_MODE",
            "EXTRA_HEADERS_JSON",
        ):
            keys.add(f"{prefix}_{suffix}")
    return sorted(keys)


def _schema_contract(model: Any) -> Dict[str, list[str]]:
    schema = model.model_json_schema()
    return {
        "required": sorted(schema.get("required", [])),
        "properties": sorted(schema.get("properties", {}).keys()),
    }


def build_current_snapshot(repo_root: Path) -> Dict[str, Any]:
    error_type_description = (
        ToolErrorPayload.model_fields["error_type"].description
        or ""
    )
    allowed_error_types = [
        token.strip()
        for token in error_type_description.split("|")
        if token.strip()
    ]

    return {
        "public_api_exports": {
            "eap.protocol": sorted(eap_protocol.__all__),
            "eap.environment": sorted(eap_environment.__all__),
            "eap.agent": sorted(eap_agent.__all__),
        },
        "workflow_schema": {
            "persisted_workflow_graph": _schema_contract(PersistedWorkflowGraph),
            "workflow_graph_node": _schema_contract(WorkflowGraphNode),
            "workflow_graph_edge": _schema_contract(WorkflowGraphEdge),
            "workflow_edge_kind_values": sorted(kind.value for kind in WorkflowEdgeKind),
        },
        "tool_error_payload_contract": {
            "fields": sorted(ToolErrorPayload.model_fields.keys()),
            "schema_required": sorted(
                ToolErrorPayload.model_json_schema().get("required", [])
            ),
            "allowed_error_types": allowed_error_types,
        },
        "settings_env_keys": _collect_settings_env_keys(DEFAULT_SETTINGS_PATH),
        "sdk_http_paths": _collect_sdk_http_paths(
            DEFAULT_TS_CLIENT_PATH,
            DEFAULT_GO_CLIENT_PATH,
        ),
    }


def evaluate_version_bump_policy(
    previous_snapshot: Optional[Dict[str, Any]],
    current_snapshot: Dict[str, Any],
    previous_package_version: Optional[str],
    current_package_version: str,
) -> Tuple[bool, str]:
    if previous_snapshot is None or previous_package_version is None:
        return True, "No comparable base revision was available for version-bump policy checks."

    if previous_snapshot == current_snapshot:
        return True, "No contract lock change detected."

    if previous_package_version == current_package_version:
        return (
            False,
            (
                "v1 contract lock changed without an explicit package version bump. "
                f"Previous version={previous_package_version}, current version={current_package_version}."
            ),
        )

    return True, "Contract lock changed with explicit package version bump."


def _git_output(repo_root: Path, args: list[str]) -> Optional[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_base_revision(repo_root: Path) -> Optional[str]:
    github_event = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    if github_event == "pull_request":
        base_ref = os.getenv("GITHUB_BASE_REF", "").strip()
        if base_ref:
            remote_base = f"origin/{base_ref}"
            if _git_output(repo_root, ["rev-parse", "--verify", remote_base]):
                merge_base = _git_output(repo_root, ["merge-base", "HEAD", remote_base])
                if merge_base:
                    return merge_base

    if _git_output(repo_root, ["rev-parse", "--verify", "HEAD~1"]):
        return "HEAD~1"

    if _git_output(repo_root, ["rev-parse", "--verify", "origin/main"]):
        merge_base = _git_output(repo_root, ["merge-base", "HEAD", "origin/main"])
        if merge_base:
            return merge_base

    return None


def _read_file_at_revision(repo_root: Path, revision: str, relative_path: str) -> Optional[str]:
    spec = f"{revision}:{relative_path}"
    return _git_output(repo_root, ["show", spec])


def _to_pretty_json(value: Dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _diff_json(expected: Dict[str, Any], actual: Dict[str, Any]) -> str:
    expected_lines = _to_pretty_json(expected).splitlines()
    actual_lines = _to_pretty_json(actual).splitlines()
    return "\n".join(
        difflib.unified_diff(
            expected_lines,
            actual_lines,
            fromfile="v1_contract_lock.snapshot",
            tofile="current_runtime_snapshot",
            lineterm="",
        )
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that the frozen v1 contract lock matches the repository runtime surface."
        )
    )
    parser.add_argument(
        "--lock-file",
        default=str(DEFAULT_LOCK_PATH),
        help="Path to the v1 contract lock JSON file.",
    )
    parser.add_argument(
        "--write-lock",
        action="store_true",
        help="Write a fresh lock file using the current runtime snapshot.",
    )
    parser.add_argument(
        "--base-revision",
        default=None,
        help="Optional git revision to compare against for version-bump policy checks.",
    )
    parser.add_argument(
        "--skip-version-history-check",
        action="store_true",
        help="Skip git-history based version-bump policy validation.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    lock_path = Path(args.lock_file).resolve()
    repo_root = REPO_ROOT
    current_package_version = _extract_project_version(DEFAULT_PYPROJECT_PATH)
    current_snapshot = build_current_snapshot(repo_root)

    if args.write_lock:
        payload = {
            "lock_format_version": 1,
            "snapshot_version": "1.0.0",
            "generated_from_package_version": current_package_version,
            "snapshot": current_snapshot,
        }
        lock_path.write_text(_to_pretty_json(payload) + "\n", encoding="utf-8")
        print(f"Wrote v1 contract lock to {lock_path}")
        return 0

    if not lock_path.exists():
        print(
            f"Missing contract lock file: {lock_path}. "
            "Run scripts/check_v1_contract.py --write-lock.",
            file=sys.stderr,
        )
        return 1

    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_snapshot = lock_payload.get("snapshot")
    if not isinstance(expected_snapshot, dict):
        print("Contract lock is missing a valid 'snapshot' object.", file=sys.stderr)
        return 1

    if current_snapshot != expected_snapshot:
        print("v1 contract snapshot mismatch detected.", file=sys.stderr)
        print(_diff_json(expected_snapshot, current_snapshot), file=sys.stderr)
        print(
            "If this is intentional, update lock + docs and bump package version explicitly.",
            file=sys.stderr,
        )
        return 1

    if not args.skip_version_history_check:
        base_revision = args.base_revision or _resolve_base_revision(repo_root)
        if base_revision:
            previous_lock_text = _read_file_at_revision(
                repo_root,
                base_revision,
                str(lock_path.relative_to(repo_root)),
            )
            previous_pyproject_text = _read_file_at_revision(
                repo_root,
                base_revision,
                str(DEFAULT_PYPROJECT_PATH.relative_to(repo_root)),
            )
            previous_snapshot: Optional[Dict[str, Any]] = None
            previous_version: Optional[str] = None

            if previous_lock_text:
                previous_snapshot = json.loads(previous_lock_text).get("snapshot")
            if previous_pyproject_text:
                previous_version = _extract_project_version_from_text(previous_pyproject_text)

            ok, message = evaluate_version_bump_policy(
                previous_snapshot=previous_snapshot,
                current_snapshot=expected_snapshot,
                previous_package_version=previous_version,
                current_package_version=current_package_version,
            )
            if not ok:
                print(message, file=sys.stderr)
                return 1
            print(message)
        else:
            print("No base revision available; skipped version-bump policy check.")

    print(f"v1 contract lock is valid for package version {current_package_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
