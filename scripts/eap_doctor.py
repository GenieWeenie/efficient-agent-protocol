#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse


CATEGORY_EXIT_BITS = {
    "env": 1,
    "config": 2,
    "connectivity": 4,
    "storage": 8,
    "tools": 16,
}

REQUIRED_ENV_KEYS = ("EAP_BASE_URL", "EAP_MODEL", "EAP_API_KEY")
ALLOWED_OPENAI_API_MODES = {"chat_completions", "responses"}


@dataclass
class DiagnosticRecord:
    check_id: str
    category: str
    status: str
    message: str
    details: Dict[str, Any]
    remediation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "remediation": self.remediation,
        }


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
    if base_url and not base_url.startswith(("http://", "https://")):
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
        if raw_mode.lower() not in ALLOWED_OPENAI_API_MODES:
            errors.append(
                f"{mode_key} must be one of: chat_completions, responses (got '{raw_mode}')."
            )
    return errors


@contextmanager
def _temporary_env(overrides: Dict[str, str]):
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _default_port_for_scheme(scheme: str) -> int:
    if scheme == "http":
        return 80
    if scheme == "https":
        return 443
    return 80


def _check_endpoint_connectivity(base_url: str, timeout_seconds: float) -> Optional[str]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        return f"Invalid host in URL: {base_url}"
    port = parsed.port or _default_port_for_scheme(parsed.scheme)
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return None
    except OSError as exc:
        return f"{host}:{port} is unreachable ({exc})"


def _build_diagnostics_payload(records: List[DiagnosticRecord]) -> Dict[str, Any]:
    failed_categories = sorted(
        {record.category for record in records if record.status == "fail"}
    )
    exit_code = 0
    for category in failed_categories:
        exit_code |= CATEGORY_EXIT_BITS.get(category, 0)
    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "summary": {
            "total_checks": len(records),
            "passed": len([record for record in records if record.status == "pass"]),
            "failed": len([record for record in records if record.status == "fail"]),
            "skipped": len([record for record in records if record.status == "skip"]),
            "failed_categories": failed_categories,
        },
        "checks": [record.to_dict() for record in records],
    }


def _record(
    records: List[DiagnosticRecord],
    check_id: str,
    category: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    remediation: str = "",
) -> None:
    records.append(
        DiagnosticRecord(
            check_id=check_id,
            category=category,
            status=status,
            message=message,
            details=details or {},
            remediation=remediation,
        )
    )


def _render_env_file(overrides: Dict[str, str]) -> str:
    env_lines = [
        "# Generated by scripts/eap_doctor.py init-env",
        "# Local mode defaults (update values as needed).",
        f"EAP_BASE_URL={overrides['EAP_BASE_URL']}",
        f"EAP_MODEL={overrides['EAP_MODEL']}",
        f"EAP_API_KEY={overrides['EAP_API_KEY']}",
        "EAP_TIMEOUT_SECONDS=60",
        "EAP_TEMPERATURE=0.0",
        f"EAP_OPENAI_API_MODE={overrides['EAP_OPENAI_API_MODE']}",
        "EAP_EXTRA_HEADERS_JSON={}",
        "",
        f"EAP_ARCHITECT_BASE_URL={overrides['EAP_BASE_URL']}",
        f"EAP_ARCHITECT_MODEL={overrides['EAP_MODEL']}",
        f"EAP_ARCHITECT_API_KEY={overrides['EAP_API_KEY']}",
        "EAP_ARCHITECT_TIMEOUT_SECONDS=60",
        "EAP_ARCHITECT_TEMPERATURE=0.0",
        f"EAP_ARCHITECT_OPENAI_API_MODE={overrides['EAP_OPENAI_API_MODE']}",
        "EAP_ARCHITECT_EXTRA_HEADERS_JSON={}",
        "",
        f"EAP_AUDITOR_BASE_URL={overrides['EAP_BASE_URL']}",
        f"EAP_AUDITOR_MODEL={overrides['EAP_MODEL']}",
        f"EAP_AUDITOR_API_KEY={overrides['EAP_API_KEY']}",
        "EAP_AUDITOR_TIMEOUT_SECONDS=60",
        "EAP_AUDITOR_TEMPERATURE=0.0",
        f"EAP_AUDITOR_OPENAI_API_MODE={overrides['EAP_OPENAI_API_MODE']}",
        "EAP_AUDITOR_EXTRA_HEADERS_JSON={}",
        "",
        "EAP_LOG_LEVEL=INFO",
        "EAP_LOG_FORMAT=json",
        "EAP_LOG_JSON=",
    ]
    return "\n".join(env_lines) + "\n"


def run_init_env(args: argparse.Namespace) -> int:
    output_path = Path(args.output).resolve()
    if output_path.exists() and not args.force:
        print(
            f"[doctor:error] Refusing to overwrite existing file without --force: {output_path}",
            file=sys.stderr,
        )
        return 1

    base_url = args.base_url.strip()
    model = args.model.strip()
    mode = args.openai_api_mode.strip().lower()

    if args.interactive:
        base_url = input(f"EAP_BASE_URL [{base_url}]: ").strip() or base_url
        model = input(f"EAP_MODEL [{model}]: ").strip() or model
        mode = input(f"EAP_OPENAI_API_MODE [{mode}]: ").strip().lower() or mode

    values = {
        "EAP_BASE_URL": base_url,
        "EAP_MODEL": model,
        "EAP_API_KEY": "not-needed",
        "EAP_OPENAI_API_MODE": mode,
    }
    errors = validate_env_values(values)
    if errors:
        print("[doctor:error] Cannot generate .env due to invalid values:", file=sys.stderr)
        for error in errors:
            print(f"[doctor:error] - {error}", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_env_file(values), encoding="utf-8")
    print(f"[doctor] Generated environment file: {output_path}")
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    env_path = Path(args.env_file).resolve()
    records: List[DiagnosticRecord] = []
    load_settings = None
    state_manager_cls = None

    if sys.version_info < (3, 9) or sys.version_info >= (3, 14):
        _record(
            records,
            check_id="python_version",
            category="tools",
            status="fail",
            message="Unsupported Python version.",
            details={"python_version": sys.version.split()[0], "supported": ">=3.9,<3.14"},
            remediation="Use Python 3.9-3.13 (`docs/troubleshooting.md#bootstrap-fails-with-python-version-error`).",
        )
    else:
        _record(
            records,
            check_id="python_version",
            category="tools",
            status="pass",
            message="Python version is supported.",
            details={"python_version": sys.version.split()[0]},
        )

    git_path = shutil.which("git")
    if git_path is None:
        _record(
            records,
            check_id="git_available",
            category="tools",
            status="fail",
            message="Git is not available in PATH.",
            remediation="Install git and rerun doctor.",
        )
    else:
        _record(
            records,
            check_id="git_available",
            category="tools",
            status="pass",
            message="Git is available.",
            details={"git_path": git_path},
        )

    try:
        from eap.protocol import StateManager as _StateManager, load_settings as _load_settings

        load_settings = _load_settings
        state_manager_cls = _StateManager
        _record(
            records,
            check_id="eap_imports",
            category="tools",
            status="pass",
            message="EAP runtime modules are importable.",
        )
    except Exception as exc:
        _record(
            records,
            check_id="eap_imports",
            category="tools",
            status="fail",
            message=f"EAP runtime modules are not importable: {exc}",
            remediation="Install dependencies and package first: `python -m pip install -e .`.",
        )

    try:
        env_values = parse_env_file(env_path)
        _record(
            records,
            check_id="env_parse",
            category="env",
            status="pass",
            message="Environment file parsed successfully.",
            details={"env_file": str(env_path)},
        )
    except (FileNotFoundError, ValueError) as exc:
        _record(
            records,
            check_id="env_parse",
            category="env",
            status="fail",
            message=str(exc),
            details={"env_file": str(env_path)},
            remediation="Generate a fresh .env with `python scripts/eap_doctor.py init-env --output .env --force`.",
        )
        env_values = {}

    env_errors = validate_env_values(env_values) if env_values else []
    if env_errors:
        _record(
            records,
            check_id="env_required_keys",
            category="env",
            status="fail",
            message="Environment validation failed.",
            details={"errors": env_errors},
            remediation="Fix .env values and rerun doctor (`docs/troubleshooting.md#environment-validation-failed-during-bootstrap`).",
        )
    elif env_values:
        _record(
            records,
            check_id="env_required_keys",
            category="env",
            status="pass",
            message="Required environment keys are valid.",
        )

    settings = None
    if env_values and not env_errors and load_settings is not None:
        try:
            with _temporary_env(env_values):
                settings = load_settings()
            _record(
                records,
                check_id="settings_load",
                category="config",
                status="pass",
                message="Runtime settings loaded successfully.",
            )
        except ValueError as exc:
            _record(
                records,
                check_id="settings_load",
                category="config",
                status="fail",
                message=f"Settings validation failed: {exc}",
                remediation="Fix configuration values based on error details (`docs/configuration.md`).",
            )
    elif env_values and load_settings is None:
        _record(
            records,
            check_id="settings_load",
            category="config",
            status="skip",
            message="Skipped because EAP runtime modules are unavailable.",
        )
    else:
        _record(
            records,
            check_id="settings_load",
            category="config",
            status="skip",
            message="Skipped because environment validation failed.",
        )

    if settings is not None and not args.skip_connectivity:
        urls = sorted({settings.architect.base_url, settings.auditor.base_url})
        failures: List[str] = []
        for base_url in urls:
            error = _check_endpoint_connectivity(base_url, timeout_seconds=args.connect_timeout_seconds)
            if error:
                failures.append(error)
        if failures:
            _record(
                records,
                check_id="provider_connectivity",
                category="connectivity",
                status="fail",
                message="Provider endpoint connectivity check failed.",
                details={"failures": failures},
                remediation="Ensure gateway host/port is reachable and base URL values are correct (`docs/troubleshooting.md#provider-selection-errors`).",
            )
        else:
            _record(
                records,
                check_id="provider_connectivity",
                category="connectivity",
                status="pass",
                message="Provider endpoint connectivity checks passed.",
                details={"base_urls": urls},
            )
    elif args.skip_connectivity:
        _record(
            records,
            check_id="provider_connectivity",
            category="connectivity",
            status="skip",
            message="Connectivity checks skipped by flag.",
        )
    else:
        _record(
            records,
            check_id="provider_connectivity",
            category="connectivity",
            status="skip",
            message="Skipped because config checks failed.",
        )

    state_db_path = Path(args.state_db_path).resolve()
    if state_manager_cls is None:
        _record(
            records,
            check_id="storage_roundtrip",
            category="storage",
            status="skip",
            message="Skipped because EAP runtime modules are unavailable.",
            details={"state_db_path": str(state_db_path)},
            remediation="Install dependencies and package first: `python -m pip install -e .`.",
        )
    else:
        try:
            state_db_path.parent.mkdir(parents=True, exist_ok=True)
            if state_db_path.exists():
                state_db_path.unlink()
            state_manager = state_manager_cls(db_path=str(state_db_path))
            pointer = state_manager.store_and_point(
                raw_data={"doctor": "ok"},
                summary="doctor storage roundtrip",
                metadata={"source": "eap_doctor"},
            )
            pointer_id = pointer["pointer_id"]
            payload = state_manager.retrieve(pointer_id)
            if "doctor" not in str(payload):
                raise RuntimeError("Unexpected storage payload content.")
            _record(
                records,
                check_id="storage_roundtrip",
                category="storage",
                status="pass",
                message="Storage roundtrip check passed.",
                details={"state_db_path": str(state_db_path), "pointer_id": pointer_id},
            )
        except Exception as exc:
            _record(
                records,
                check_id="storage_roundtrip",
                category="storage",
                status="fail",
                message=f"Storage roundtrip check failed: {exc}",
                details={"state_db_path": str(state_db_path)},
                remediation="Check filesystem write permissions and rerun (`docs/troubleshooting.md#database--state-issues`).",
            )
    diagnostics = _build_diagnostics_payload(records)
    diagnostics["env_file"] = str(env_path)
    diagnostics["state_db_path"] = str(state_db_path)
    output_json_text = json.dumps(diagnostics, indent=2, sort_keys=True)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json_text + "\n", encoding="utf-8")
        print(f"[doctor] Wrote diagnostics JSON: {output_path}")

    print("[doctor] Check summary:")
    for record in records:
        print(f"[doctor] - {record.status.upper():4} [{record.category}] {record.check_id}: {record.message}")

    exit_code = diagnostics["exit_code"]
    if exit_code == 0:
        print("[doctor] All checks passed.")
    else:
        print(f"[doctor] Checks failed with categorized exit code: {exit_code}", file=sys.stderr)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guided onboarding and environment diagnostics for EAP."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_env = subparsers.add_parser("init-env", help="Generate a runnable local .env file.")
    init_env.add_argument("--output", default=".env", help="Output .env file path.")
    init_env.add_argument("--force", action="store_true", help="Overwrite existing output file.")
    init_env.add_argument("--interactive", action="store_true", help="Prompt for values interactively.")
    init_env.add_argument("--base-url", default="http://localhost:1234", help="EAP base URL.")
    init_env.add_argument("--model", default="nemotron-orchestrator-8b", help="EAP model name.")
    init_env.add_argument(
        "--openai-api-mode",
        default="chat_completions",
        help="OpenAI-compatible API mode (chat_completions or responses).",
    )

    doctor = subparsers.add_parser("doctor", help="Run environment diagnostics.")
    doctor.add_argument("--env-file", default=".env", help="Environment file to validate.")
    doctor.add_argument(
        "--state-db-path",
        default="artifacts/doctor/doctor_state.db",
        help="Path used for storage roundtrip checks.",
    )
    doctor.add_argument(
        "--skip-connectivity",
        action="store_true",
        help="Skip provider endpoint connectivity checks.",
    )
    doctor.add_argument(
        "--connect-timeout-seconds",
        type=float,
        default=1.5,
        help="Socket timeout for connectivity checks.",
    )
    doctor.add_argument("--output-json", default="", help="Write machine-readable JSON diagnostics to this path.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv or sys.argv[1:])
    if args.command == "init-env":
        return run_init_env(args)
    if args.command == "doctor":
        return run_doctor(args)
    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
