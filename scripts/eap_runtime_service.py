#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Sequence

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.environment.tools import ANALYZE_SCHEMA, FETCH_SCHEMA, analyze_data, fetch_user_data
from eap.protocol import StateManager
from eap.runtime import EAPRuntimeHTTPServer
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
        help="Optional admin bearer token for /v1/eap/* endpoints.",
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
    return parser.parse_args(argv)


def _register_default_tools(registry: ToolRegistry) -> None:
    # Keep default remote surface narrow for safer out-of-box operation.
    registry.register("fetch_user_data", fetch_user_data, FETCH_SCHEMA)
    registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)


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


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.port <= 0 or args.port > 65535:
        print("[runtime:error] --port must be between 1 and 65535.")
        return 1
    bearer_token = args.bearer_token.strip()
    try:
        scoped_tokens, active_policy_profile = _load_scoped_auth_config(
            args.scoped_auth_config,
            default_policy_profile=args.policy_profile,
        )
    except Exception as exc:
        print(f"[runtime:error] failed to load --scoped-auth-config: {exc}")
        return 1

    if not bearer_token and not scoped_tokens:
        print("[runtime:error] provide --bearer-token and/or --scoped-auth-config.")
        return 1

    db_path = Path(args.db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    state_manager = StateManager(db_path=str(db_path))
    registry = ToolRegistry()
    _register_default_tools(registry)
    executor = AsyncLocalExecutor(state_manager, registry)

    server = EAPRuntimeHTTPServer(
        executor=executor,
        state_manager=state_manager,
        host=args.host,
        port=args.port,
        required_bearer_token=bearer_token or None,
        scoped_bearer_tokens=scoped_tokens or None,
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
    print(f"[runtime] scoped_auth_tokens={len(scoped_tokens)}")
    print("[runtime] tools=fetch_user_data,analyze_data")

    try:
        while not stop_event.wait(timeout=0.5):
            pass
    finally:
        server.stop()
        print("[runtime] stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
