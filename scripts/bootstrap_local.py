#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List


REQUIRED_ENV_KEYS = ("EAP_BASE_URL", "EAP_MODEL", "EAP_API_KEY")
ALLOWED_OPENAI_API_MODES = {"chat_completions", "responses"}


def parse_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Environment file was not found: {path}")

    values: Dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in raw_line:
            raise ValueError(f"{path}:{line_number} must contain KEY=VALUE format.")
        key, value = raw_line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError(f"{path}:{line_number} has an empty key.")
        values[normalized_key] = value.strip()
    return values


def validate_env_values(values: Dict[str, str]) -> List[str]:
    errors: List[str] = []

    for key in REQUIRED_ENV_KEYS:
        if not values.get(key, "").strip():
            errors.append(f"{key} is required and cannot be empty.")

    base_url = values.get("EAP_BASE_URL", "").strip()
    if base_url and not re.match(r"^https?://", base_url):
        errors.append("EAP_BASE_URL must start with http:// or https://.")

    openai_api_mode_keys: Iterable[str] = (
        "EAP_OPENAI_API_MODE",
        "EAP_ARCHITECT_OPENAI_API_MODE",
        "EAP_AUDITOR_OPENAI_API_MODE",
    )
    for mode_key in openai_api_mode_keys:
        raw_mode = values.get(mode_key, "").strip()
        if not raw_mode:
            continue
        normalized_mode = raw_mode.lower()
        if normalized_mode not in ALLOWED_OPENAI_API_MODES:
            errors.append(
                f"{mode_key} must be one of: chat_completions, responses (got '{raw_mode}')."
            )

    return errors


async def _execute_smoke_macro(db_path: Path, artifact_path: Path) -> None:
    from eap.environment import AsyncLocalExecutor, ToolRegistry
    from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall

    def echo_text(text: str) -> str:
        return f"ECHO:{text}"

    echo_schema = {
        "name": "echo_text",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }

    db_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    state_manager = StateManager(db_path=str(db_path))
    registry = ToolRegistry()
    registry.register("echo_text", echo_text, echo_schema)
    executor = AsyncLocalExecutor(state_manager, registry)

    macro = BatchedMacroRequest(
        steps=[ToolCall(step_id="step_echo", tool_name="echo_text", arguments={"text": "hello eap"})],
        retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
    )
    result = await executor.execute_macro(macro)

    pointer_id = result.get("pointer_id")
    if not isinstance(pointer_id, str) or not pointer_id:
        raise RuntimeError("Smoke macro did not return a valid pointer_id.")

    metadata = result.get("metadata") or {}
    run_id = metadata.get("execution_run_id")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeError("Smoke macro did not return metadata.execution_run_id.")

    summary = state_manager.get_execution_summary(run_id)
    trace_events = [event.model_dump(mode="json") for event in state_manager.list_trace_events(run_id)]

    payload = {
        "run_id": run_id,
        "pointer_id": pointer_id,
        "pointer_payload": state_manager.retrieve(pointer_id),
        "summary": summary,
        "trace_event_count": len(trace_events),
        "trace_events": trace_events,
    }
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="EAP local bootstrap helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-env", help="Validate local .env settings.")
    validate_parser.add_argument("--env-file", default=".env", help="Path to environment file.")

    smoke_parser = subparsers.add_parser("run-smoke", help="Run minimal macro and emit trace artifact.")
    smoke_parser.add_argument(
        "--artifact-dir",
        default="artifacts/bootstrap",
        help="Directory for bootstrap artifacts.",
    )
    smoke_parser.add_argument(
        "--db-path",
        default="artifacts/bootstrap/bootstrap_state.db",
        help="State DB path used by the smoke workflow.",
    )
    smoke_parser.add_argument(
        "--artifact-file-name",
        default="bootstrap_trace.json",
        help="Bootstrap artifact file name.",
    )

    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    if args.command == "validate-env":
        env_file = Path(args.env_file).resolve()
        try:
            values = parse_env_file(env_file)
        except (FileNotFoundError, ValueError) as exc:
            print(f"[bootstrap:error] {exc}", file=sys.stderr)
            return 1

        errors = validate_env_values(values)
        if errors:
            print("[bootstrap:error] Environment validation failed:", file=sys.stderr)
            for error in errors:
                print(f"[bootstrap:error] - {error}", file=sys.stderr)
            return 1

        print(f"[bootstrap] Environment file is valid: {env_file}")
        return 0

    if args.command == "run-smoke":
        artifact_dir = Path(args.artifact_dir).resolve()
        db_path = Path(args.db_path).resolve()
        artifact_path = artifact_dir / args.artifact_file_name
        try:
            asyncio.run(_execute_smoke_macro(db_path=db_path, artifact_path=artifact_path))
        except Exception as exc:
            print(f"[bootstrap:error] Smoke workflow failed: {exc}", file=sys.stderr)
            return 1

        print(f"[bootstrap] Smoke workflow succeeded.")
        print(f"[bootstrap] Trace artifact: {artifact_path}")
        print(f"[bootstrap] State DB: {db_path}")
        return 0

    print(f"[bootstrap:error] Unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
