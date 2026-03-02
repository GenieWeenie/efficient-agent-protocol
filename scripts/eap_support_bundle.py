#!/usr/bin/env python3
"""Generate a support bundle for EAP operator troubleshooting.

Collects environment info, configuration state, database health,
recent telemetry, and diagnostic artifacts into a single directory
that can be shared with support or used for post-mortem analysis.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_script(command: List[str], cwd: str, timeout: int = 60) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout": result.stdout[-5000:] if len(result.stdout) > 5000 else result.stdout,
            "stderr": result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "command": " ".join(command),
            "returncode": -1,
            "stdout": "",
            "stderr": f"Timed out after {timeout}s",
        }
    except Exception as exc:
        return {
            "command": " ".join(command),
            "returncode": -1,
            "stdout": "",
            "stderr": str(exc),
        }


def _collect_environment(verbose: bool = False) -> Dict[str, Any]:
    env_info: Dict[str, Any] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "hostname": platform.node(),
        "cwd": os.getcwd(),
    }
    eap_env_vars = {
        key: ("***" if "KEY" in key or "SECRET" in key else value)
        for key, value in sorted(os.environ.items())
        if key.startswith("EAP_")
    }
    env_info["eap_environment_variables"] = eap_env_vars
    return env_info


def _collect_git_info() -> Dict[str, Any]:
    git_info: Dict[str, Any] = {}
    sha_result = _run_script(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT))
    git_info["sha"] = sha_result["stdout"].strip() if sha_result["returncode"] == 0 else "unknown"
    branch_result = _run_script(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(REPO_ROOT))
    git_info["branch"] = branch_result["stdout"].strip() if branch_result["returncode"] == 0 else "unknown"
    status_result = _run_script(["git", "status", "--short"], cwd=str(REPO_ROOT))
    git_info["dirty_files"] = len(status_result["stdout"].strip().splitlines()) if status_result["returncode"] == 0 else -1
    return git_info


def _collect_package_info() -> Dict[str, Any]:
    pip_result = _run_script([sys.executable, "-m", "pip", "show", "efficient-agent-protocol"], cwd=str(REPO_ROOT))
    if pip_result["returncode"] == 0:
        return {"installed": True, "details": pip_result["stdout"]}
    return {"installed": False, "details": pip_result["stderr"]}


def generate_bundle(
    db_path: str,
    output_root: str,
    env_file: str = ".env",
    verbose: bool = False,
    include_telemetry: bool = True,
    include_healthcheck: bool = True,
) -> Dict[str, Any]:
    bundle_name = f"eap-support-bundle-{_utc_timestamp_slug()}"
    bundle_dir = Path(output_root).resolve() / bundle_name
    bundle_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "generated_at_utc": _now_utc_iso(),
        "bundle_name": bundle_name,
        "bundle_dir": str(bundle_dir),
        "sections": [],
    }

    # 1. Environment info
    env_info = _collect_environment(verbose=verbose)
    _write_json(bundle_dir / "environment.json", env_info)
    manifest["sections"].append("environment.json")
    if verbose:
        print("[bundle] Collected environment info.")

    # 2. Git info
    git_info = _collect_git_info()
    _write_json(bundle_dir / "git_info.json", git_info)
    manifest["sections"].append("git_info.json")
    if verbose:
        print("[bundle] Collected git info.")

    # 3. Package info
    pkg_info = _collect_package_info()
    _write_json(bundle_dir / "package_info.json", pkg_info)
    manifest["sections"].append("package_info.json")

    # 4. Doctor diagnostics
    doctor_result = _run_script(
        [sys.executable, str(REPO_ROOT / "scripts" / "eap_doctor.py"), "doctor",
         "--env-file", env_file,
         "--output-json", str(bundle_dir / "doctor_diagnostics.json")],
        cwd=str(REPO_ROOT),
    )
    _write_json(bundle_dir / "doctor_run.json", doctor_result)
    manifest["sections"].append("doctor_diagnostics.json")
    manifest["sections"].append("doctor_run.json")
    if verbose:
        print(f"[bundle] Doctor exited with code {doctor_result['returncode']}.")

    # 5. State health check
    if include_healthcheck:
        healthcheck_result = _run_script(
            [sys.executable, str(REPO_ROOT / "scripts" / "eap_state_healthcheck.py"),
             "--db-path", db_path,
             "--output-json", str(bundle_dir / "state_healthcheck.json"),
             "--verbose"],
            cwd=str(REPO_ROOT),
        )
        _write_json(bundle_dir / "healthcheck_run.json", healthcheck_result)
        manifest["sections"].append("state_healthcheck.json")
        if verbose:
            print("[bundle] Collected state health check.")

    # 6. Telemetry snapshot
    if include_telemetry and Path(db_path).exists():
        telemetry_dir = bundle_dir / "telemetry"
        telemetry_result = _run_script(
            [sys.executable, str(REPO_ROOT / "scripts" / "export_telemetry_pack.py"),
             "--db-path", db_path,
             "--output-dir", str(telemetry_dir),
             "--limit-runs", "100"],
            cwd=str(REPO_ROOT),
        )
        _write_json(bundle_dir / "telemetry_run.json", telemetry_result)
        manifest["sections"].append("telemetry/")
        if verbose:
            print("[bundle] Exported telemetry snapshot.")

    # 7. Write manifest
    manifest["total_sections"] = len(manifest["sections"])
    _write_json(bundle_dir / "bundle_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a support bundle for EAP troubleshooting and incident analysis."
    )
    parser.add_argument(
        "--db-path",
        default="agent_state.db",
        help="Path to the SQLite state database.",
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/support_bundles",
        help="Root directory for support bundle output.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file for doctor diagnostics.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress during bundle generation.",
    )
    parser.add_argument(
        "--skip-telemetry",
        action="store_true",
        help="Skip telemetry export (faster, smaller bundle).",
    )
    parser.add_argument(
        "--skip-healthcheck",
        action="store_true",
        help="Skip state DB health check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = generate_bundle(
            db_path=args.db_path,
            output_root=args.output_root,
            env_file=args.env_file,
            verbose=args.verbose,
            include_telemetry=not args.skip_telemetry,
            include_healthcheck=not args.skip_healthcheck,
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
