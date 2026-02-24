#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Sequence

import requests


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test for EAP self-hosted runtime stack.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="Base URL for runtime API (default: http://127.0.0.1:8080).",
    )
    parser.add_argument(
        "--bearer-token",
        required=True,
        help="Bearer token expected by the runtime.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="HTTP request timeout in seconds (default: 10).",
    )
    parser.add_argument(
        "--artifact-path",
        default="artifacts/self_hosted/self_hosted_smoke.json",
        help="JSON artifact output path.",
    )
    return parser.parse_args(argv)


def _raise_for_status(response: requests.Response, context: str) -> None:
    if response.status_code < 400:
        return
    raise RuntimeError(
        f"{context} failed ({response.status_code}): {response.text[:400]}"
    )


def run_smoke(
    base_url: str,
    bearer_token: str,
    timeout_seconds: float,
) -> Dict[str, Any]:
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {bearer_token}"}

    execute_response = requests.post(
        f"{base}/v1/eap/macro/execute",
        headers=headers,
        json={
            "macro": {
                "steps": [
                    {
                        "step_id": "smoke_fetch_user",
                        "tool_name": "fetch_user_data",
                        "arguments": {"query": "smoke-user-001"},
                    }
                ]
            }
        },
        timeout=timeout_seconds,
    )
    _raise_for_status(execute_response, "execute_macro")
    execute_payload = execute_response.json()

    pointer_id = execute_payload.get("pointer_id")
    run_id = (execute_payload.get("metadata") or {}).get("execution_run_id")
    if not isinstance(pointer_id, str) or not pointer_id:
        raise RuntimeError("execute_macro response is missing pointer_id")
    if not isinstance(run_id, str) or not run_id:
        raise RuntimeError("execute_macro response is missing metadata.execution_run_id")

    run_response = requests.get(
        f"{base}/v1/eap/runs/{run_id}",
        headers=headers,
        timeout=timeout_seconds,
    )
    _raise_for_status(run_response, "get_run")
    run_payload = run_response.json()
    if run_payload.get("status") != "succeeded":
        raise RuntimeError(f"run status is not succeeded: {run_payload.get('status')}")
    total_steps = (run_payload.get("summary") or {}).get("total_steps")
    if total_steps != 1:
        raise RuntimeError(f"expected total_steps=1, got {total_steps!r}")

    pointer_response = requests.get(
        f"{base}/v1/eap/pointers/{pointer_id}/summary",
        headers=headers,
        timeout=timeout_seconds,
    )
    _raise_for_status(pointer_response, "get_pointer_summary")
    pointer_payload = pointer_response.json()

    return {
        "base_url": base,
        "execute": execute_payload,
        "run": run_payload,
        "pointer_summary": pointer_payload,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    artifact_path = Path(args.artifact_path).resolve()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        payload = run_smoke(
            base_url=args.base_url,
            bearer_token=args.bearer_token.strip(),
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        print(f"[self-hosted-smoke:error] {exc}")
        return 1

    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("[self-hosted-smoke] succeeded.")
    print(f"[self-hosted-smoke] artifact={artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
