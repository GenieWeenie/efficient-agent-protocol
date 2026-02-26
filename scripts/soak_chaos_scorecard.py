#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


@dataclass
class ChaosScenarioResult:
    name: str
    passed: bool
    duration_ms: float
    details: Dict[str, Any]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_git_sha() -> str:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight)


def _build_executor(registry: ToolRegistry) -> Tuple[AsyncLocalExecutor, StateManager, str]:
    fd, db_path = tempfile.mkstemp(prefix="eap-soak-chaos-", suffix=".db")
    os.close(fd)
    manager = StateManager(db_path=db_path)
    return AsyncLocalExecutor(manager, registry), manager, db_path


class _SoakServiceTool:
    def __init__(self) -> None:
        self._attempts_by_operation: Dict[str, int] = {}

    def __call__(self, operation_id: str, mode: str = "stable") -> str:
        attempts = self._attempts_by_operation.get(operation_id, 0) + 1
        self._attempts_by_operation[operation_id] = attempts

        if mode == "transient_timeout":
            if attempts == 1:
                raise TimeoutError(f"transient timeout for {operation_id}")
            return f"ok:{operation_id}"
        if mode == "retry_storm":
            if attempts <= 2:
                raise TimeoutError(f"retry storm timeout for {operation_id} attempt={attempts}")
            return f"ok:{operation_id}"
        if mode == "dependency_outage":
            raise ConnectionError(f"dependency outage for {operation_id}")
        if mode == "stable":
            return f"ok:{operation_id}"
        raise ValueError(f"unsupported mode: {mode}")


def _service_tool_schema(name: str = "service_tool") -> Dict[str, Any]:
    return {
        "name": name,
        "parameters": {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"},
                "mode": {"type": "string"},
            },
            "required": ["operation_id"],
            "additionalProperties": False,
        },
    }


def _echo_tool(value: str) -> str:
    return value


def _echo_tool_schema() -> Dict[str, Any]:
    return {
        "name": "echo_tool",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }


def _count_retry_events(state_manager: StateManager, run_id: str) -> int:
    events = state_manager.list_trace_events(run_id)
    return sum(1 for event in events if event.event_type.value == "retried")


def _run_soak_flow(*, iterations: int, chaos_interval: int) -> Dict[str, Any]:
    if iterations <= 0:
        raise ValueError("iterations must be > 0")
    if chaos_interval <= 0:
        raise ValueError("chaos_interval must be > 0")

    registry = ToolRegistry()
    service_tool = _SoakServiceTool()
    registry.register("service_tool", service_tool, _service_tool_schema())
    executor, state_manager, db_path = _build_executor(registry)
    durations_ms: List[float] = []
    failures: List[Dict[str, Any]] = []
    retry_events_total = 0
    run_ids: List[str] = []
    successful_runs = 0
    try:
        for idx in range(iterations):
            mode = "transient_timeout" if (idx % chaos_interval == 0) else "stable"
            macro = BatchedMacroRequest(
                steps=[
                    ToolCall(
                        step_id=f"soak_step_{idx}",
                        tool_name="service_tool",
                        arguments={"operation_id": f"soak_op_{idx}", "mode": mode},
                    )
                ],
                retry_policy=RetryPolicy(
                    max_attempts=2,
                    initial_delay_seconds=0.0,
                    backoff_multiplier=1.0,
                    retryable_error_types=["TimeoutError"],
                ),
            )
            started = time.perf_counter()
            result = asyncio.run(executor.execute_macro(macro))
            duration_ms = (time.perf_counter() - started) * 1000.0
            durations_ms.append(duration_ms)

            metadata = result.get("metadata", {})
            run_id = str(metadata.get("execution_run_id", ""))
            if run_id:
                run_ids.append(run_id)
                retry_events_total += _count_retry_events(state_manager, run_id)

            status = str(metadata.get("status", "ok"))
            if status == "error":
                failures.append(
                    {
                        "index": idx,
                        "mode": mode,
                        "status": status,
                        "error_type": metadata.get("error_type", "unknown"),
                    }
                )
            else:
                successful_runs += 1

        total_runs = len(durations_ms)
        failure_count = len(failures)
        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failure_count,
            "pass_rate": (float(successful_runs) / float(total_runs)) if total_runs else 0.0,
            "failure_rate": (float(failure_count) / float(total_runs)) if total_runs else 0.0,
            "latency_ms": {
                "p50": _percentile(durations_ms, 50.0),
                "p95": _percentile(durations_ms, 95.0),
                "max": max(durations_ms) if durations_ms else 0.0,
            },
            "retry_events_total": retry_events_total,
            "chaos_interval": chaos_interval,
            "sample_failures": failures[:10],
            "run_ids_sample": run_ids[:10],
        }
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def _run_chaos_dependency_outage() -> ChaosScenarioResult:
    registry = ToolRegistry()
    service_tool = _SoakServiceTool()
    registry.register("service_tool", service_tool, _service_tool_schema())
    registry.register("echo_tool", _echo_tool, _echo_tool_schema())
    executor, state_manager, db_path = _build_executor(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="outage_step",
                    tool_name="service_tool",
                    arguments={"operation_id": "outage_op", "mode": "dependency_outage"},
                ),
                ToolCall(
                    step_id="dependent_step",
                    tool_name="echo_tool",
                    arguments={"value": "$step:outage_step"},
                ),
            ],
            retry_policy=RetryPolicy(max_attempts=1, initial_delay_seconds=0.0, backoff_multiplier=1.0),
        )
        result = asyncio.run(executor.execute_macro(macro))
        metadata = result.get("metadata", {})
        run_id = str(metadata.get("execution_run_id", ""))
        retry_events = _count_retry_events(state_manager, run_id) if run_id else 0
        passed = metadata.get("status") == "error" and metadata.get("error_type") == "dependency_error"
        details = {
            "status": metadata.get("status"),
            "error_type": metadata.get("error_type"),
            "retry_events": retry_events,
        }
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ChaosScenarioResult(
        name="dependency_outage",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_chaos_timeout_recovery() -> ChaosScenarioResult:
    registry = ToolRegistry()
    service_tool = _SoakServiceTool()
    registry.register("service_tool", service_tool, _service_tool_schema())
    executor, state_manager, db_path = _build_executor(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="timeout_step",
                    tool_name="service_tool",
                    arguments={"operation_id": "timeout_recovery", "mode": "transient_timeout"},
                )
            ],
            retry_policy=RetryPolicy(
                max_attempts=2,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                retryable_error_types=["TimeoutError"],
            ),
        )
        result = asyncio.run(executor.execute_macro(macro))
        metadata = result.get("metadata", {})
        run_id = str(metadata.get("execution_run_id", ""))
        retry_events = _count_retry_events(state_manager, run_id) if run_id else 0
        passed = metadata.get("status") != "error" and retry_events >= 1
        details = {
            "status": metadata.get("status", "ok"),
            "error_type": metadata.get("error_type"),
            "retry_events": retry_events,
        }
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ChaosScenarioResult(
        name="timeout_recovery",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_chaos_retry_storm(*, steps: int) -> ChaosScenarioResult:
    if steps <= 0:
        raise ValueError("retry_storm steps must be > 0")
    registry = ToolRegistry()
    service_tool = _SoakServiceTool()
    registry.register("service_tool", service_tool, _service_tool_schema())
    executor, state_manager, db_path = _build_executor(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id=f"storm_step_{idx}",
                    tool_name="service_tool",
                    arguments={"operation_id": f"storm_op_{idx}", "mode": "retry_storm"},
                )
                for idx in range(steps)
            ],
            retry_policy=RetryPolicy(
                max_attempts=3,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
                retryable_error_types=["TimeoutError"],
            ),
        )
        result = asyncio.run(executor.execute_macro(macro))
        metadata = result.get("metadata", {})
        run_id = str(metadata.get("execution_run_id", ""))
        retry_events = _count_retry_events(state_manager, run_id) if run_id else 0
        expected_min_retry_events = steps * 2
        passed = metadata.get("status") != "error" and retry_events >= expected_min_retry_events
        details = {
            "status": metadata.get("status", "ok"),
            "error_type": metadata.get("error_type"),
            "retry_events": retry_events,
            "expected_min_retry_events": expected_min_retry_events,
            "steps": steps,
        }
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ChaosScenarioResult(
        name="retry_storm",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_chaos_suite(*, retry_storm_steps: int) -> Dict[str, Any]:
    scenarios = [
        _run_chaos_dependency_outage(),
        _run_chaos_timeout_recovery(),
        _run_chaos_retry_storm(steps=retry_storm_steps),
    ]
    passed = sum(1 for scenario in scenarios if scenario.passed)
    scenario_rows: List[Dict[str, Any]] = []
    for scenario in scenarios:
        scenario_rows.append(
            {
                "name": scenario.name,
                "passed": scenario.passed,
                "duration_ms": scenario.duration_ms,
                "details": scenario.details,
            }
        )
    return {
        "total": len(scenarios),
        "passed": passed,
        "pass_rate": (float(passed) / float(len(scenarios))) if scenarios else 0.0,
        "scenarios": scenario_rows,
    }


def _evaluate_gate(
    *,
    scorecard: Dict[str, Any],
    thresholds: Dict[str, Any],
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    failures: List[str] = []
    soak = scorecard["soak"]
    chaos = scorecard["chaos"]

    soak_thresholds = thresholds.get("soak", {})
    min_runs = int(soak_thresholds.get("min_runs", 1))
    max_failure_rate = float(soak_thresholds.get("max_failure_rate", 1.0))
    max_latency_p95_ms = float(soak_thresholds.get("max_latency_p95_ms", float("inf")))
    min_retry_events_total = int(soak_thresholds.get("min_retry_events_total", 0))

    if int(soak["total_runs"]) < min_runs:
        failures.append(f"soak total_runs below threshold: {soak['total_runs']} < {min_runs}")
    if float(soak["failure_rate"]) > max_failure_rate:
        failures.append(
            f"soak failure_rate above threshold: {float(soak['failure_rate']):.6f} > {max_failure_rate:.6f}"
        )
    if float(soak["latency_ms"]["p95"]) > max_latency_p95_ms:
        failures.append(
            f"soak latency p95 above threshold: {float(soak['latency_ms']['p95']):.3f} > {max_latency_p95_ms:.3f}"
        )
    if int(soak["retry_events_total"]) < min_retry_events_total:
        failures.append(
            f"soak retry events below threshold: {int(soak['retry_events_total'])} < {min_retry_events_total}"
        )

    chaos_thresholds = thresholds.get("chaos", {})
    min_chaos_pass_rate = float(chaos_thresholds.get("min_pass_rate", 0.0))
    if float(chaos["pass_rate"]) < min_chaos_pass_rate:
        failures.append(
            f"chaos pass_rate below threshold: {float(chaos['pass_rate']):.6f} < {min_chaos_pass_rate:.6f}"
        )

    required_scenarios = [str(name) for name in chaos_thresholds.get("required_scenarios", [])]
    scenario_map = {str(row["name"]): row for row in chaos.get("scenarios", [])}
    for scenario_name in required_scenarios:
        if scenario_name not in scenario_map:
            failures.append(f"missing required chaos scenario result: {scenario_name}")
            continue
        if not bool(scenario_map[scenario_name].get("passed", False)):
            failures.append(f"chaos scenario failed: {scenario_name}")

    scenario_requirements = chaos_thresholds.get("scenario_requirements", {})
    if isinstance(scenario_requirements, dict):
        for scenario_name, requirements in scenario_requirements.items():
            row = scenario_map.get(str(scenario_name))
            if row is None:
                continue
            req = requirements if isinstance(requirements, dict) else {}
            min_retry_events = int(req.get("min_retry_events", 0))
            retry_events = int((row.get("details") or {}).get("retry_events", 0))
            if retry_events < min_retry_events:
                failures.append(
                    f"chaos scenario {scenario_name} retry_events below threshold: "
                    f"{retry_events} < {min_retry_events}"
                )

    baseline_metrics = baseline.get("metrics", {})
    regression = thresholds.get("regression", {})
    baseline_soak_failure_rate = float(baseline_metrics.get("soak_failure_rate", soak["failure_rate"]))
    baseline_soak_p95 = float(baseline_metrics.get("soak_latency_p95_ms", soak["latency_ms"]["p95"]))
    baseline_chaos_pass_rate = float(baseline_metrics.get("chaos_pass_rate", chaos["pass_rate"]))
    max_failure_rate_increase = float(regression.get("max_failure_rate_increase", 0.0))
    max_latency_p95_ratio_increase = float(regression.get("max_latency_p95_ratio_increase", 0.0))
    max_chaos_pass_rate_drop = float(regression.get("max_chaos_pass_rate_drop", 0.0))

    if float(soak["failure_rate"]) > (baseline_soak_failure_rate + max_failure_rate_increase):
        failures.append(
            "soak failure_rate regressed above allowed increase: "
            f"current={float(soak['failure_rate']):.6f}, "
            f"baseline={baseline_soak_failure_rate:.6f}, "
            f"allowed_increase={max_failure_rate_increase:.6f}"
        )
    if baseline_soak_p95 > 0.0:
        allowed_p95 = baseline_soak_p95 * (1.0 + max_latency_p95_ratio_increase)
        if float(soak["latency_ms"]["p95"]) > allowed_p95:
            failures.append(
                "soak latency p95 regressed above allowed ratio increase: "
                f"current={float(soak['latency_ms']['p95']):.3f}, baseline={baseline_soak_p95:.3f}, "
                f"allowed={allowed_p95:.3f}"
            )
    if float(chaos["pass_rate"]) < (baseline_chaos_pass_rate - max_chaos_pass_rate_drop):
        failures.append(
            "chaos pass_rate regressed below allowed drop: "
            f"current={float(chaos['pass_rate']):.6f}, baseline={baseline_chaos_pass_rate:.6f}, "
            f"allowed_drop={max_chaos_pass_rate_drop:.6f}"
        )

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "thresholds": thresholds,
    }


def _build_trend(scorecard: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    baseline_metrics = baseline.get("metrics", {})
    soak = scorecard["soak"]
    chaos = scorecard["chaos"]
    current = {
        "soak_failure_rate": float(soak["failure_rate"]),
        "soak_latency_p95_ms": float(soak["latency_ms"]["p95"]),
        "chaos_pass_rate": float(chaos["pass_rate"]),
    }
    deltas = {
        "soak_failure_rate": current["soak_failure_rate"] - float(
            baseline_metrics.get("soak_failure_rate", current["soak_failure_rate"])
        ),
        "soak_latency_p95_ms": current["soak_latency_p95_ms"] - float(
            baseline_metrics.get("soak_latency_p95_ms", current["soak_latency_p95_ms"])
        ),
        "chaos_pass_rate": current["chaos_pass_rate"] - float(
            baseline_metrics.get("chaos_pass_rate", current["chaos_pass_rate"])
        ),
    }
    return {
        "current": current,
        "baseline": baseline_metrics,
        "delta_vs_baseline": deltas,
    }


def _render_markdown(scorecard: Dict[str, Any]) -> str:
    gate = scorecard["gate"]
    status = "PASS" if gate["passed"] else "FAIL"
    lines = [
        "# Soak + Chaos Reliability Scorecard",
        "",
        f"- Generated: `{scorecard['generated_at_utc']}`",
        f"- Git SHA: `{scorecard['git_sha']}`",
        f"- Python: `{scorecard['python_version']}`",
        f"- Platform: `{scorecard['platform']}`",
        f"- Gate: **{status}**",
        "",
        "## Soak Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total runs | `{scorecard['soak']['total_runs']}` |",
        f"| Pass rate | `{scorecard['soak']['pass_rate']:.6f}` |",
        f"| Failure rate | `{scorecard['soak']['failure_rate']:.6f}` |",
        f"| Retry events total | `{scorecard['soak']['retry_events_total']}` |",
        f"| Latency p95 (ms) | `{scorecard['soak']['latency_ms']['p95']:.3f}` |",
        f"| Latency max (ms) | `{scorecard['soak']['latency_ms']['max']:.3f}` |",
        "",
        "## Chaos Scenarios",
        "",
        "| Scenario | Passed | Duration (ms) | Retry Events |",
        "| --- | --- | ---: | ---: |",
    ]
    for scenario in scorecard["chaos"]["scenarios"]:
        retry_events = int((scenario.get("details") or {}).get("retry_events", 0))
        lines.append(
            f"| `{scenario['name']}` | "
            f"`{'yes' if scenario['passed'] else 'no'}` | "
            f"`{float(scenario['duration_ms']):.3f}` | `{retry_events}` |"
        )
    lines.extend(["", "## Gate Result", ""])
    if gate["failures"]:
        for failure in gate["failures"]:
            lines.append(f"- [ ] {failure}")
    else:
        lines.append("- [x] Soak + chaos thresholds satisfied.")
    return "\n".join(lines) + "\n"


def _build_scorecard(*, soak_iterations: int, soak_chaos_interval: int, retry_storm_steps: int) -> Dict[str, Any]:
    soak = _run_soak_flow(iterations=soak_iterations, chaos_interval=soak_chaos_interval)
    chaos = _run_chaos_suite(retry_storm_steps=retry_storm_steps)
    return {
        "generated_at_utc": _now_utc_iso(),
        "schema_version": "1.0",
        "git_sha": _current_git_sha(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "soak": soak,
        "chaos": chaos,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run soak + chaos reliability harness and emit CI-gated scorecard artifacts."
    )
    parser.add_argument("--output-dir", default="artifacts/soak_chaos", help="Output artifact directory.")
    parser.add_argument(
        "--threshold-config",
        default="docs/soak_chaos_thresholds.json",
        help="Threshold config JSON path.",
    )
    parser.add_argument(
        "--baseline",
        default="docs/soak_chaos_baseline.json",
        help="Baseline metrics JSON path for regression checks.",
    )
    parser.add_argument(
        "--soak-iterations",
        type=int,
        default=60,
        help="Number of macro runs in soak flow (default: 60).",
    )
    parser.add_argument(
        "--soak-chaos-interval",
        type=int,
        default=7,
        help="Every N soak runs, inject transient timeout chaos (default: 7).",
    )
    parser.add_argument(
        "--retry-storm-steps",
        type=int,
        default=6,
        help="Number of steps in retry-storm chaos scenario (default: 6).",
    )
    parser.add_argument(
        "--no-fail-on-regression",
        action="store_true",
        help="Do not exit non-zero when thresholds fail.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    thresholds = _load_json(Path(args.threshold_config))
    baseline = _load_json(Path(args.baseline))

    scorecard = _build_scorecard(
        soak_iterations=args.soak_iterations,
        soak_chaos_interval=args.soak_chaos_interval,
        retry_storm_steps=args.retry_storm_steps,
    )
    scorecard["thresholds"] = thresholds
    scorecard["baseline"] = baseline
    scorecard["gate"] = _evaluate_gate(scorecard=scorecard, thresholds=thresholds, baseline=baseline)
    trend = _build_trend(scorecard=scorecard, baseline=baseline)
    scorecard["trend"] = trend

    json_path = output_dir / "scorecard.json"
    md_path = output_dir / "scorecard.md"
    trend_path = output_dir / "trend.json"
    history_path = output_dir / "history.ndjson"

    _write_json(json_path, scorecard)
    md_path.write_text(_render_markdown(scorecard), encoding="utf-8")
    _write_json(trend_path, trend)
    history_line = json.dumps(scorecard, sort_keys=True)
    if history_path.exists():
        history_path.write_text(history_path.read_text(encoding="utf-8") + history_line + "\n", encoding="utf-8")
    else:
        history_path.write_text(history_line + "\n", encoding="utf-8")

    payload = {
        "gate_passed": scorecard["gate"]["passed"],
        "soak_runs": scorecard["soak"]["total_runs"],
        "chaos_scenarios": scorecard["chaos"]["total"],
        "scorecard_file": str(json_path.resolve()),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if scorecard["gate"]["passed"] or args.no_fail_on_regression:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
