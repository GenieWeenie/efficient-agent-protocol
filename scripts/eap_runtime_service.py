#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Sequence

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import ANALYZE_SCHEMA, FETCH_SCHEMA, analyze_data, fetch_user_data
from eap.protocol import ExecutionLimits, StateManager, ToolExecutionLimit, load_settings
from eap.runtime import EAPRuntimeHTTPServer
from eap.runtime.guardrails import normalize_concurrency_limits, normalize_rate_limit_rules
from eap.runtime.policy_profiles import DEFAULT_POLICY_PROFILE, build_scoped_token_policies


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run EAP runtime HTTP service.")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host for runtime HTTP server (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port for runtime HTTP server (default: 8080).",
    )
    parser.add_argument(
        "--db-path",
        default="agent_state.db",
        help="SQLite path for state persistence (default: agent_state.db).",
    )
    parser.add_argument(
        "--bearer-token",
        default="",
        help=(
            "Optional admin bearer token for /v1/eap/* endpoints. "
            "Avoid using on the command line in production — prefer the "
            "EAP_RUNTIME_BEARER_TOKEN environment variable or "
            "--bearer-token-file (e.g. for Kubernetes secret mounts) so the "
            "secret is not visible in `ps`/`/proc/<pid>/cmdline`."
        ),
    )
    parser.add_argument(
        "--bearer-token-file",
        default="",
        help=(
            "Path to a file containing the bearer token. The first line of "
            "the file is read and stripped. Useful for k8s/Docker secret "
            "mounts. Mutually exclusive with --bearer-token."
        ),
    )
    parser.add_argument(
        "--allow-unauthenticated-local-dev",
        action="store_true",
        help=(
            "Explicit local-development escape hatch. Allows unauthenticated full-scope runtime access "
            "only when binding to 127.0.0.1, localhost, or ::1. Never use in production."
        ),
    )
    parser.add_argument(
        "--scoped-auth-config",
        default="",
        help=(
            "Optional JSON file defining scoped bearer tokens. "
            "Format supports policy profiles + templates: "
            "{\"policy_profile\":\"strict\",\"tokens\":[{\"token\":\"...\",\"actor_id\":\"...\",\"template\":\"viewer\"}]}"
        ),
    )
    parser.add_argument(
        "--policy-profile",
        default=DEFAULT_POLICY_PROFILE,
        choices=("strict", "balanced", "trusted"),
        help=(
            "Default policy profile applied to scoped token entries when per-token profile is omitted "
            "(default: strict)."
        ),
    )
    parser.add_argument(
        "--guardrails-config",
        default="",
        help=(
            "Optional JSON file defining runtime rate limits and concurrency limits. "
            "Format: {\"rate_limits\":{\"macro_execute\":{\"max_requests\":60,\"window_seconds\":60}},"
            "\"concurrency\":{\"global_inflight\":12,\"execute_inflight\":6,\"resume_inflight\":6,"
            "\"per_run_resume_inflight\":1}}"
        ),
    )
    parser.add_argument(
        "--max-request-body-bytes",
        type=int,
        default=1_000_000,
        help="Maximum accepted runtime request body size in bytes (default: 1000000).",
    )
    return parser.parse_args(argv)


BEARER_TOKEN_ENV_VAR = "EAP_RUNTIME_BEARER_TOKEN"


def _resolve_bearer_token(args: argparse.Namespace) -> str:
    """Resolve the bearer token from (in order) flag, file, env var.

    Passing the token on the command line is supported but discouraged because
    it is visible to anyone with ``ps``/``/proc`` access on the host. Prefer the
    ``EAP_RUNTIME_BEARER_TOKEN`` environment variable or ``--bearer-token-file``.

    Raises ``ValueError`` if more than one source is provided or if a referenced
    file is unreadable/empty.
    """
    flag_token = args.bearer_token.strip()
    file_path = (args.bearer_token_file or "").strip()

    sources_provided = sum(1 for value in (flag_token, file_path) if value)
    if sources_provided > 1:
        raise ValueError("--bearer-token and --bearer-token-file are mutually exclusive.")

    if file_path:
        try:
            raw = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"failed to read --bearer-token-file '{file_path}': {exc}") from exc
        token = raw.splitlines()[0].strip() if raw else ""
        if not token:
            raise ValueError(f"--bearer-token-file '{file_path}' is empty.")
        return token

    if flag_token:
        return flag_token

    env_token = os.environ.get(BEARER_TOKEN_ENV_VAR, "").strip()
    return env_token


def _register_default_tools(registry: ToolRegistry) -> None:
    # Keep default remote surface narrow for safer out-of-box operation.
    registry.register("fetch_user_data", fetch_user_data, FETCH_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)


def _load_default_execution_limits() -> ExecutionLimits:
    settings = load_settings()
    return ExecutionLimits(
        max_global_concurrency=settings.executor.max_global_concurrency,
        max_total_runtime_seconds=settings.executor.max_total_runtime_seconds,
        max_reference_resolution_depth=settings.executor.max_reference_resolution_depth,
        global_requests_per_second=settings.executor.global_requests_per_second,
        global_burst_capacity=settings.executor.global_burst_capacity,
        per_tool={
            tool_name: ToolExecutionLimit(
                max_concurrency=limit.max_concurrency,
                requests_per_second=limit.requests_per_second,
                burst_capacity=limit.burst_capacity,
            )
            for tool_name, limit in settings.executor.per_tool_limits.items()
        },
    )


def _load_scoped_auth_config(
    path: str,
    *,
    default_policy_profile: str,
) -> tuple[Dict[str, Dict[str, Any]], str]:
    if not path.strip():
        return {}, default_policy_profile
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return build_scoped_token_policies(
        payload,
        default_policy_profile=default_policy_profile,
    )


def _load_guardrails_config(
    path: str,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if not path.strip():
        normalized_rate_limits = normalize_rate_limit_rules(None)
        normalized_concurrency_limits = normalize_concurrency_limits(None)
        return (
            {},
            {},
            normalized_rate_limits,
            {
                "global_inflight": normalized_concurrency_limits.global_inflight,
                "execute_inflight": normalized_concurrency_limits.execute_inflight,
                "resume_inflight": normalized_concurrency_limits.resume_inflight,
                "per_run_resume_inflight": normalized_concurrency_limits.per_run_resume_inflight,
            },
        )

    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("guardrails config must be a JSON object.")

    rate_limits = payload.get("rate_limits") or {}
    concurrency_limits = payload.get("concurrency") or {}
    if not isinstance(rate_limits, dict):
        raise ValueError("guardrails config 'rate_limits' must be an object.")
    if not isinstance(concurrency_limits, dict):
        raise ValueError("guardrails config 'concurrency' must be an object.")

    normalized_rate_limits = normalize_rate_limit_rules(rate_limits)
    normalized_concurrency_limits = normalize_concurrency_limits(concurrency_limits)
    return (
        rate_limits,
        concurrency_limits,
        normalized_rate_limits,
        {
            "global_inflight": normalized_concurrency_limits.global_inflight,
            "execute_inflight": normalized_concurrency_limits.execute_inflight,
            "resume_inflight": normalized_concurrency_limits.resume_inflight,
            "per_run_resume_inflight": normalized_concurrency_limits.per_run_resume_inflight,
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.port <= 0 or args.port > 65535:
        print("[runtime:error] --port must be between 1 and 65535.")
        return 1
    if args.max_request_body_bytes <= 0:
        print("[runtime:error] --max-request-body-bytes must be greater than 0.")
        return 1
    try:
        bearer_token = _resolve_bearer_token(args)
    except ValueError as exc:
        print(f"[runtime:error] {exc}")
        return 1
    try:
        scoped_tokens, active_policy_profile = _load_scoped_auth_config(
            args.scoped_auth_config,
            default_policy_profile=args.policy_profile,
        )
    except Exception as exc:
        print(f"[runtime:error] failed to load --scoped-auth-config: {exc}")
        return 1
    try:
        rate_limit_rules, concurrency_limits, normalized_rate_limits, normalized_concurrency_limits = (
            _load_guardrails_config(args.guardrails_config)
        )
    except Exception as exc:
        print(f"[runtime:error] failed to load --guardrails-config: {exc}")
        return 1

    if args.allow_unauthenticated_local_dev and args.host.strip().lower() not in {"127.0.0.1", "localhost", "::1"}:
        print("[runtime:error] --allow-unauthenticated-local-dev requires --host 127.0.0.1, localhost, or ::1.")
        return 1

    if not bearer_token and not scoped_tokens and not args.allow_unauthenticated_local_dev:
        print("[runtime:error] provide --bearer-token and/or --scoped-auth-config.")
        return 1

    db_path = Path(args.db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    state_manager = StateManager(db_path=str(db_path))
    registry = ToolRegistry()
    _register_default_tools(registry)
    try:
        default_execution_limits = _load_default_execution_limits()
    except Exception as exc:
        print(f"[runtime:error] failed to load executor settings: {exc}")
        return 1
    executor = AsyncLocalExecutor(state_manager, registry, default_execution_limits=default_execution_limits)

    server = EAPRuntimeHTTPServer(
        executor=executor,
        state_manager=state_manager,
        host=args.host,
        port=args.port,
        required_bearer_token=bearer_token or None,
        scoped_bearer_tokens=scoped_tokens or None,
        rate_limit_rules=rate_limit_rules or None,
        concurrency_limits=concurrency_limits or None,
        max_request_body_bytes=args.max_request_body_bytes,
        allow_unauthenticated_local_dev=args.allow_unauthenticated_local_dev,
    ).start()

    stop_event = threading.Event()

    def _handle_signal(signum, _frame) -> None:  # type: ignore[no-untyped-def]
        print(f"[runtime] received signal {signum}; shutting down.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    print("[runtime] EAP runtime server started.")
    print(f"[runtime] base_url={server.base_url}")
    print(f"[runtime] db_path={db_path}")
    print(f"[runtime] policy_profile={active_policy_profile}")
    print(f"[runtime] allow_unauthenticated_local_dev={args.allow_unauthenticated_local_dev}")
    if args.allow_unauthenticated_local_dev:
        print("[runtime:warning] unauthenticated local-dev auth is enabled; do not expose this service remotely.")
    print(f"[runtime] scoped_auth_tokens={len(scoped_tokens)}")
    print(f"[runtime] rate_limits={json.dumps(normalized_rate_limits, sort_keys=True, default=lambda o: o.__dict__)}")
    print(f"[runtime] concurrency_limits={json.dumps(normalized_concurrency_limits, sort_keys=True)}")
    print(f"[runtime] max_request_body_bytes={args.max_request_body_bytes}")
    print("[runtime] tools=fetch_user_data,analyze_data")

    try:
        while not stop_event.wait(timeout=0.5):
            pass
    finally:
        server.stop()
        try:
            state_manager.close()
        except Exception as exc:  # pragma: no cover - defensive teardown
            print(f"[runtime:warning] state_manager.close failed: {exc}")
        print("[runtime] stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
