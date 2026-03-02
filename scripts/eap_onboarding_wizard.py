#!/usr/bin/env python3
"""Guided onboarding wizard for new EAP users.

Walks through environment setup, configuration validation, and
runs a minimal smoke test to confirm everything works.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw or default


def _run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Guided onboarding for new EAP users.")
    parser.add_argument("--non-interactive", action="store_true", help="Use defaults without prompting.")
    args = parser.parse_args()

    print("=" * 60)
    print("  EAP Onboarding Wizard")
    print("=" * 60)
    print()

    # Step 1: Check Python version
    print("[1/5] Checking Python version...")
    version = sys.version_info
    if version < (3, 9) or version >= (3, 14):
        print(f"  ERROR: Python {version.major}.{version.minor} is not supported. Use 3.9-3.13.")
        return 1
    print(f"  OK: Python {version.major}.{version.minor}.{version.micro}")
    print()

    # Step 2: Check/install package
    print("[2/5] Checking EAP installation...")
    pip_check = _run([sys.executable, "-m", "pip", "show", "efficient-agent-protocol"], check=False)
    if pip_check.returncode != 0:
        print("  EAP is not installed. Installing in editable mode...")
        install = _run([sys.executable, "-m", "pip", "install", "-e", str(REPO_ROOT)], check=False)
        if install.returncode != 0:
            print(f"  ERROR: Installation failed.\n{install.stderr}")
            return 1
        print("  OK: Installed successfully.")
    else:
        print("  OK: Already installed.")
    print()

    # Step 3: Generate .env
    print("[3/5] Setting up environment configuration...")
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        print(f"  .env already exists at {env_path}")
    else:
        if args.non_interactive:
            base_url = "http://localhost:1234"
            model = "nemotron-orchestrator-8b"
            api_mode = "chat_completions"
        else:
            base_url = _prompt("  LLM gateway base URL", "http://localhost:1234")
            model = _prompt("  Model name", "nemotron-orchestrator-8b")
            api_mode = _prompt("  API mode (chat_completions or responses)", "chat_completions")

        doctor_cmd = [
            sys.executable, str(REPO_ROOT / "scripts" / "eap_doctor.py"),
            "init-env",
            "--output", str(env_path),
            "--base-url", base_url,
            "--model", model,
            "--openai-api-mode", api_mode,
        ]
        result = _run(doctor_cmd, check=False)
        if result.returncode != 0:
            print(f"  ERROR: Failed to generate .env.\n{result.stderr}")
            return 1
        print(f"  OK: Generated {env_path}")
    print()

    # Step 4: Run doctor
    print("[4/5] Running environment diagnostics...")
    doctor_result = _run(
        [sys.executable, str(REPO_ROOT / "scripts" / "eap_doctor.py"), "doctor",
         "--env-file", str(env_path), "--skip-connectivity"],
        check=False,
    )
    print(doctor_result.stdout)
    if doctor_result.returncode != 0:
        print("  WARNING: Some checks failed. Review the output above.")
        print("  You can fix issues and re-run: python scripts/eap_doctor.py doctor")
    else:
        print("  OK: All diagnostics passed.")
    print()

    # Step 5: Run smoke test
    print("[5/5] Running minimal smoke test...")
    smoke_cmd = [sys.executable, "-c", """
import asyncio, tempfile, os
from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall

def echo(value: str) -> str:
    return value

schema = {"name": "echo", "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False}}
registry = ToolRegistry()
registry.register("echo", echo, schema)
fd, db = tempfile.mkstemp(suffix=".db")
os.close(fd)
sm = StateManager(db_path=db)
executor = AsyncLocalExecutor(sm, registry)
macro = BatchedMacroRequest(steps=[ToolCall(step_id="s1", tool_name="echo", arguments={"value": "hello"})], retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0))
result = asyncio.run(executor.execute_macro(macro))
output = sm.retrieve(result["pointer_id"])
assert output == "hello", f"Expected 'hello', got '{output}'"
os.remove(db)
print("SMOKE_OK")
"""]
    smoke_result = _run(smoke_cmd, check=False)
    if "SMOKE_OK" in smoke_result.stdout:
        print("  OK: Smoke test passed.")
    else:
        print(f"  ERROR: Smoke test failed.\n{smoke_result.stderr}")
        return 1

    print()
    print("=" * 60)
    print("  Onboarding complete!")
    print()
    print("  Next steps:")
    print("    1. Start the dashboard:  streamlit run app.py")
    print("    2. Try an example:       python examples/01_minimal_macro.py")
    print("    3. Read the docs:        docs/architecture.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
