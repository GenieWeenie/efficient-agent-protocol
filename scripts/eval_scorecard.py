#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eap.environment import AsyncLocalExecutor, ToolRegistry
from eap.protocol import BatchedMacroRequest, RetryPolicy, StateManager, ToolCall


@dataclass
class ScenarioResult:
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
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight


def _build_executor_with_registry(registry: ToolRegistry) -> Tuple[AsyncLocalExecutor, StateManager, str]:
    fd, db_path = tempfile.mkstemp(prefix="eap-eval-", suffix=".db")
    os.close(fd)
    state_manager = StateManager(db_path=db_path)
    return AsyncLocalExecutor(state_manager, registry), state_manager, db_path


def _run_correctness_reference_flow() -> ScenarioResult:
    def uppercase_text(value: str) -> str:
        return value.upper()

    def append_status(base: str, suffix: str) -> str:
        return f"{base}:{suffix}"

    upper_schema = {
        "name": "uppercase_text",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    append_schema = {
        "name": "append_status",
        "parameters": {
            "type": "object",
            "properties": {
                "base": {"type": "string"},
                "suffix": {"type": "string"},
            },
            "required": ["base", "suffix"],
            "additionalProperties": False,
        },
    }
    registry = ToolRegistry()
    registry.register("uppercase_text", uppercase_text, upper_schema)
    registry.register("append_status", append_status, append_schema)
    executor, state_manager, db_path = _build_executor_with_registry(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_upper",
                    tool_name="uppercase_text",
                    arguments={"value": "eap"},
                ),
                ToolCall(
                    step_id="step_append",
                    tool_name="append_status",
                    arguments={"base": "$step:step_upper", "suffix": "ok"},
                ),
            ],
            retry_policy=RetryPolicy(
                max_attempts=1,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
            ),
        )
        result = asyncio.run(executor.execute_macro(macro))
        final_output = state_manager.retrieve(result["pointer_id"])
        passed = final_output == "EAP:ok"
        details = {
            "expected": "EAP:ok",
            "actual": final_output,
            "run_id": result["metadata"]["execution_run_id"],
        }
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ScenarioResult(
        name="correctness_reference_flow",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_reliability_retry_flow() -> ScenarioResult:
    class TimeoutThenSuccessTool:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, value: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("transient timeout")
            return value

    tool = TimeoutThenSuccessTool()
    tool_schema = {
        "name": "retry_tool",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    registry = ToolRegistry()
    registry.register("retry_tool", tool, tool_schema)
    executor, state_manager, db_path = _build_executor_with_registry(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(
                    step_id="step_retry",
                    tool_name="retry_tool",
                    arguments={"value": "ok"},
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
        events = state_manager.list_trace_events(result["metadata"]["execution_run_id"])
        event_types = [event.event_type.value for event in events]
        passed = tool.calls == 2 and "retried" in event_types and event_types[-1] == "completed"
        details = {"calls": tool.calls, "events": event_types}
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ScenarioResult(
        name="reliability_retry_flow",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_reliability_dependency_flow() -> ScenarioResult:
    def always_fail(value: str) -> str:
        raise RuntimeError(f"forced failure:{value}")

    def echo_tool(value: str) -> str:
        return value

    fail_schema = {
        "name": "fail_tool",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    echo_schema = {
        "name": "echo_tool",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    registry = ToolRegistry()
    registry.register("fail_tool", always_fail, fail_schema)
    registry.register("echo_tool", echo_tool, echo_schema)
    executor, _state_manager, db_path = _build_executor_with_registry(registry)
    started = time.perf_counter()
    try:
        macro = BatchedMacroRequest(
            steps=[
                ToolCall(step_id="step_fail", tool_name="fail_tool", arguments={"value": "x"}),
                ToolCall(
                    step_id="step_dep",
                    tool_name="echo_tool",
                    arguments={"value": "$step:step_fail"},
                ),
            ],
            retry_policy=RetryPolicy(
                max_attempts=1,
                initial_delay_seconds=0.0,
                backoff_multiplier=1.0,
            ),
        )
        result = asyncio.run(executor.execute_macro(macro))
        passed = (
            result.get("metadata", {}).get("status") == "error"
            and result.get("metadata", {}).get("error_type") == "dependency_error"
        )
        details = {
            "status": result.get("metadata", {}).get("status"),
            "error_type": result.get("metadata", {}).get("error_type"),
        }
    except Exception as exc:
        passed = False
        details = {"error": str(exc)}
    finally:
        duration_ms = (time.perf_counter() - started) * 1000.0
        if os.path.exists(db_path):
            os.remove(db_path)
    return ScenarioResult(
        name="reliability_dependency_flow",
        passed=passed,
        duration_ms=duration_ms,
        details=details,
    )


def _run_latency_samples(iterations: int) -> Dict[str, Any]:
    def echo_latency(value: str) -> str:
        return value

    echo_schema = {
        "name": "echo_latency",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    }
    registry = ToolRegistry()
    registry.register("echo_latency", echo_latency, echo_schema)
    executor, _state_manager, db_path = _build_executor_with_registry(registry)
    samples_ms: List[float] = []
    try:
        for idx in range(iterations):
            started = time.perf_counter()
            macro = BatchedMacroRequest(
                steps=[
                    ToolCall(
                        step_id=f"lat_step_{idx}",
                        tool_name="echo_latency",
                        arguments={"value": "ok"},
                    )
                ],
                retry_policy=RetryPolicy(
                    max_attempts=1,
                    initial_delay_seconds=0.0,
                    backoff_multiplier=1.0,
                ),
            )
            asyncio.run(executor.execute_macro(macro))
            samples_ms.append((time.perf_counter() - started) * 1000.0)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
    return {
        "samples": iterations,
        "mean": round(statistics.fmean(samples_ms), 3),
        "p50": round(_percentile(samples_ms, 50.0), 3),
        "p95": round(_percentile(samples_ms, 95.0), 3),
        "max": round(max(samples_ms) if samples_ms else 0.0, 3),
        "raw_samples_ms": [round(value, 3) for value in samples_ms],
    }


def _load_json_file(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evaluate_gate(
    scorecard: Dict[str, Any],
    thresholds: Dict[str, Any],
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    failures: List[str] = []
    correctness_rate = float(scorecard["correctness"]["pass_rate"])
    reliability_rate = float(scorecard["reliability"]["pass_rate"])
    latency_p95 = float(scorecard["latency_ms"]["p95"])
    latency_max = float(scorecard["latency_ms"]["max"])

    correctness_min = float(thresholds["correctness"]["min_pass_rate"])
    reliability_min = float(thresholds["reliability"]["min_pass_rate"])
    latency_p95_max = float(thresholds["latency_ms"]["max_p95"])
    latency_max_max = float(thresholds["latency_ms"]["max_max"])

    if correctness_rate < correctness_min:
        failures.append(
            f"correctness pass_rate {correctness_rate:.3f} below threshold {correctness_min:.3f}"
        )
    if reliability_rate < reliability_min:
        failures.append(
            f"reliability pass_rate {reliability_rate:.3f} below threshold {reliability_min:.3f}"
        )
    if latency_p95 > latency_p95_max:
        failures.append(f"latency p95 {latency_p95:.3f}ms above max {latency_p95_max:.3f}ms")
    if latency_max > latency_max_max:
        failures.append(f"latency max {latency_max:.3f}ms above max {latency_max_max:.3f}ms")

    if baseline:
        regression = thresholds.get("regression", {})
        baseline_metrics = baseline.get("metrics", {})
        baseline_correctness = float(baseline_metrics.get("correctness_pass_rate", correctness_rate))
        baseline_reliability = float(baseline_metrics.get("reliability_pass_rate", reliability_rate))
        baseline_latency_p95 = float(baseline_metrics.get("latency_p95_ms", latency_p95))
        baseline_latency_max = float(baseline_metrics.get("latency_max_ms", latency_max))
        max_pass_rate_drop = float(regression.get("max_pass_rate_drop", 0.0))
        max_latency_p95_ratio = float(regression.get("max_latency_p95_ratio_increase", 0.0))
        max_latency_max_ratio = float(regression.get("max_latency_max_ratio_increase", 0.0))

        if correctness_rate < (baseline_correctness - max_pass_rate_drop):
            failures.append(
                "correctness pass_rate regressed below allowed drop: "
                f"current={correctness_rate:.3f}, baseline={baseline_correctness:.3f}, "
                f"max_drop={max_pass_rate_drop:.3f}"
            )
        if reliability_rate < (baseline_reliability - max_pass_rate_drop):
            failures.append(
                "reliability pass_rate regressed below allowed drop: "
                f"current={reliability_rate:.3f}, baseline={baseline_reliability:.3f}, "
                f"max_drop={max_pass_rate_drop:.3f}"
            )

        allowed_latency_p95 = baseline_latency_p95 * (1.0 + max_latency_p95_ratio)
        allowed_latency_max = baseline_latency_max * (1.0 + max_latency_max_ratio)
        if latency_p95 > allowed_latency_p95:
            failures.append(
                "latency p95 regressed above allowed ratio: "
                f"current={latency_p95:.3f}ms, baseline={baseline_latency_p95:.3f}ms, "
                f"allowed={allowed_latency_p95:.3f}ms"
            )
        if latency_max > allowed_latency_max:
            failures.append(
                "latency max regressed above allowed ratio: "
                f"current={latency_max:.3f}ms, baseline={baseline_latency_max:.3f}ms, "
                f"allowed={allowed_latency_max:.3f}ms"
            )

    return {"passed": not failures, "failures": failures}


def _build_trend(scorecard: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    baseline_metrics = baseline.get("metrics", {}) if baseline else {}
    current_metrics = {
        "correctness_pass_rate": float(scorecard["correctness"]["pass_rate"]),
        "reliability_pass_rate": float(scorecard["reliability"]["pass_rate"]),
        "latency_p95_ms": float(scorecard["latency_ms"]["p95"]),
        "latency_max_ms": float(scorecard["latency_ms"]["max"]),
    }
    metrics: List[Dict[str, Any]] = []
    for key, current_value in current_metrics.items():
        baseline_value = baseline_metrics.get(key)
        if baseline_value is None:
            delta = None
        else:
            baseline_value = float(baseline_value)
            delta = round(current_value - baseline_value, 3)
        metrics.append(
            {
                "name": key,
                "baseline": baseline_value,
                "current": round(current_value, 3),
                "delta": delta,
            }
        )
    return {
        "generated_at_utc": _now_utc_iso(),
        "metrics": metrics,
    }


def _render_markdown(scorecard: Dict[str, Any]) -> str:
    gate = scorecard["gate"]
    status_text = "PASS" if gate["passed"] else "FAIL"
    lines = [
        "# EAP Evaluation Scorecard",
        "",
        f"- Generated: `{scorecard['generated_at_utc']}`",
        f"- Git SHA: `{scorecard['git_sha']}`",
        f"- Python: `{scorecard['python_version']}`",
        f"- Platform: `{scorecard['platform']}`",
        f"- Gate: **{status_text}**",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Correctness pass rate | `{scorecard['correctness']['pass_rate']:.3f}` |",
        f"| Reliability pass rate | `{scorecard['reliability']['pass_rate']:.3f}` |",
        f"| Latency p50 (ms) | `{scorecard['latency_ms']['p50']:.3f}` |",
        f"| Latency p95 (ms) | `{scorecard['latency_ms']['p95']:.3f}` |",
        f"| Latency max (ms) | `{scorecard['latency_ms']['max']:.3f}` |",
        "",
        "## Regression Gate",
        "",
    ]
    if gate["failures"]:
        for failure in gate["failures"]:
            lines.append(f"- [ ] {failure}")
    else:
        lines.append("- [x] All thresholds satisfied.")
    return "\n".join(lines) + "\n"


def _build_scorecard(latency_iterations: int) -> Dict[str, Any]:
    correctness_scenarios = [_run_correctness_reference_flow()]
    reliability_scenarios = [_run_reliability_retry_flow(), _run_reliability_dependency_flow()]
    latency = _run_latency_samples(iterations=latency_iterations)

    correctness_passed = sum(1 for scenario in correctness_scenarios if scenario.passed)
    reliability_passed = sum(1 for scenario in reliability_scenarios if scenario.passed)
    correctness_pass_rate = (
        float(correctness_passed) / float(len(correctness_scenarios)) if correctness_scenarios else 0.0
    )
    reliability_pass_rate = (
        float(reliability_passed) / float(len(reliability_scenarios)) if reliability_scenarios else 0.0
    )

    return {
        "schema_version": "1.0",
        "generated_at_utc": _now_utc_iso(),
        "git_sha": _current_git_sha(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "correctness": {
            "total": len(correctness_scenarios),
            "passed": correctness_passed,
            "pass_rate": correctness_pass_rate,
            "scenarios": [
                {
                    "name": scenario.name,
                    "passed": scenario.passed,
                    "duration_ms": round(scenario.duration_ms, 3),
                    "details": scenario.details,
                }
                for scenario in correctness_scenarios
            ],
        },
        "reliability": {
            "total": len(reliability_scenarios),
            "passed": reliability_passed,
            "pass_rate": reliability_pass_rate,
            "scenarios": [
                {
                    "name": scenario.name,
                    "passed": scenario.passed,
                    "duration_ms": round(scenario.duration_ms, 3),
                    "details": scenario.details,
                }
                for scenario in reliability_scenarios
            ],
        },
        "latency_ms": latency,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run EAP evaluation harness and emit scorecard + trend artifacts."
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/eval",
        help="Directory for scorecard artifacts (default: artifacts/eval).",
    )
    parser.add_argument(
        "--threshold-config",
        default="docs/eval_thresholds.json",
        help="Path to threshold configuration JSON.",
    )
    parser.add_argument(
        "--baseline",
        default="docs/eval_baseline.json",
        help="Path to baseline metrics JSON used for regression comparisons.",
    )
    parser.add_argument(
        "--latency-iterations",
        type=int,
        default=20,
        help="Number of latency sample runs (default: 20).",
    )
    parser.add_argument(
        "--no-fail-on-regression",
        action="store_true",
        help="Do not exit with non-zero status if thresholds fail.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    threshold_path = Path(args.threshold_config)
    baseline_path = Path(args.baseline)

    thresholds = _load_json_file(threshold_path)
    baseline: Dict[str, Any] = {}
    if baseline_path.exists():
        baseline = _load_json_file(baseline_path)

    scorecard = _build_scorecard(latency_iterations=args.latency_iterations)
    scorecard["thresholds"] = thresholds
    scorecard["baseline"] = baseline
    scorecard["gate"] = _evaluate_gate(scorecard=scorecard, thresholds=thresholds, baseline=baseline)
    trend = _build_trend(scorecard=scorecard, baseline=baseline)
    scorecard["trend"] = trend

    json_path = output_dir / "scorecard.json"
    md_path = output_dir / "scorecard.md"
    trend_path = output_dir / "trend.json"
    history_path = output_dir / "history.ndjson"

    json_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown(scorecard), encoding="utf-8")
    trend_path.write_text(json.dumps(trend, indent=2, sort_keys=True), encoding="utf-8")
    history_path.write_text(
        history_path.read_text(encoding="utf-8") + json.dumps(scorecard, sort_keys=True) + "\n"
        if history_path.exists()
        else json.dumps(scorecard, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    gate = scorecard["gate"]
    print(
        json.dumps(
            {
                "gate_passed": gate["passed"],
                "failures": gate["failures"],
                "output_dir": str(output_dir),
                "scorecard_file": str(json_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if gate["passed"] or args.no_fail_on_regression:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
