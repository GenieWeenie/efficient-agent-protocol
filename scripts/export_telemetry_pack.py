#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    rank = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(math.floor(rank))
    upper_index = int(math.ceil(rank))
    lower = float(sorted_values[lower_index])
    upper = float(sorted_values[upper_index])
    if lower_index == upper_index:
        return lower
    weight = rank - lower_index
    return lower + (upper - lower) * weight


def _safe_json_load(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _aggregate_numeric(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {
            "count": 0,
            "avg": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    float_values = [float(value) for value in values]
    return {
        "count": len(float_values),
        "avg": round(sum(float_values) / len(float_values), 6),
        "p50": round(_percentile(float_values, 50.0), 6),
        "p95": round(_percentile(float_values, 95.0), 6),
        "p99": round(_percentile(float_values, 99.0), 6),
        "max": round(max(float_values), 6),
    }


def _load_runs(conn: sqlite3.Connection, limit: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT run_id, started_at_utc, completed_at_utc, total_steps, succeeded_steps, failed_steps, total_duration_ms
        FROM execution_run_summaries
        ORDER BY completed_at_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    runs: List[Dict[str, Any]] = []
    for row in rows:
        runs.append(
            {
                "run_id": row[0],
                "started_at_utc": row[1],
                "completed_at_utc": row[2],
                "total_steps": int(row[3]),
                "succeeded_steps": int(row[4]),
                "failed_steps": int(row[5]),
                "total_duration_ms": float(row[6]),
            }
        )
    return runs


def _load_trace_rows(conn: sqlite3.Connection, run_ids: Sequence[str]) -> List[Dict[str, Any]]:
    if not run_ids:
        return []
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT event_id, run_id, step_id, tool_name, event_type, timestamp_utc, attempt, duration_ms,
               retry_delay_seconds, error_payload
        FROM execution_trace_events
        WHERE run_id IN ({placeholders})
        ORDER BY event_id ASC
        """,
        tuple(run_ids),
    ).fetchall()
    payload: List[Dict[str, Any]] = []
    for row in rows:
        error_payload = _safe_json_load(row[9])
        payload.append(
            {
                "event_id": int(row[0]),
                "run_id": row[1],
                "step_id": row[2],
                "tool_name": row[3],
                "event_type": row[4],
                "timestamp_utc": row[5],
                "attempt": int(row[6]),
                "duration_ms": float(row[7]) if row[7] is not None else None,
                "retry_delay_seconds": float(row[8]) if row[8] is not None else None,
                "error_payload": error_payload,
            }
        )
    return payload


def _load_diagnostics(conn: sqlite3.Connection, run_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" for _ in run_ids)
    rows = conn.execute(
        f"""
        SELECT run_id, updated_at_utc, payload_json
        FROM execution_run_diagnostics
        WHERE run_id IN ({placeholders})
        ORDER BY updated_at_utc DESC
        """,
        tuple(run_ids),
    ).fetchall()
    diagnostics: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        run_id = row[0]
        if run_id in diagnostics:
            continue
        diagnostics[run_id] = {
            "updated_at_utc": row[1],
            "payload": _safe_json_load(row[2]),
        }
    return diagnostics


def _build_retries_view(trace_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    retry_rows = [row for row in trace_rows if row["event_type"] == "retried"]
    tool_counts: Dict[str, int] = {}
    step_counts: Dict[str, int] = {}
    run_counts: Dict[str, int] = {}

    for row in retry_rows:
        tool_name = row["tool_name"]
        step_key = f"{row['run_id']}::{row['step_id']}"
        run_id = row["run_id"]
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        step_counts[step_key] = step_counts.get(step_key, 0) + 1
        run_counts[run_id] = run_counts.get(run_id, 0) + 1

    return {
        "retry_event_total": len(retry_rows),
        "runs_with_retries": len(run_counts),
        "by_tool": [
            {"tool_name": tool_name, "retry_count": count}
            for tool_name, count in sorted(tool_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "by_step": [
            {"run_step": run_step, "retry_count": count}
            for run_step, count in sorted(step_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "by_run": [
            {"run_id": run_id, "retry_count": count}
            for run_id, count in sorted(run_counts.items(), key=lambda item: item[1], reverse=True)
        ],
    }


def _build_fail_reasons_view(trace_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    failed_rows = [row for row in trace_rows if row["event_type"] == "failed"]
    error_type_counts: Dict[str, int] = {}
    tool_counts: Dict[str, int] = {}
    message_counts: Dict[str, int] = {}

    recent_failures: List[Dict[str, Any]] = []
    for row in reversed(failed_rows):
        error_payload = row.get("error_payload") or {}
        error_type = error_payload.get("error_type", "unknown")
        message = error_payload.get("message", "")

        error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1
        tool_counts[row["tool_name"]] = tool_counts.get(row["tool_name"], 0) + 1
        if message:
            message_counts[message] = message_counts.get(message, 0) + 1

        recent_failures.append(
            {
                "run_id": row["run_id"],
                "step_id": row["step_id"],
                "tool_name": row["tool_name"],
                "timestamp_utc": row["timestamp_utc"],
                "error_type": error_type,
                "message": message,
            }
        )
        if len(recent_failures) >= 20:
            break

    return {
        "failed_event_total": len(failed_rows),
        "error_type_counts": error_type_counts,
        "top_failure_tools": [
            {"tool_name": tool_name, "failure_count": count}
            for tool_name, count in sorted(tool_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "top_failure_messages": [
            {"message": message, "count": count}
            for message, count in sorted(message_counts.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "recent_failures": recent_failures,
    }


def _build_latency_view(trace_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    completed_durations = [
        float(row["duration_ms"])
        for row in trace_rows
        if row["event_type"] == "completed" and row["duration_ms"] is not None
    ]
    per_tool: Dict[str, List[float]] = {}
    for row in trace_rows:
        if row["event_type"] != "completed" or row["duration_ms"] is None:
            continue
        per_tool.setdefault(row["tool_name"], []).append(float(row["duration_ms"]))

    return {
        "overall": _aggregate_numeric(completed_durations),
        "per_tool": {
            tool_name: _aggregate_numeric(values)
            for tool_name, values in sorted(per_tool.items())
        },
    }


def _build_saturation_view(
    runs: Sequence[Dict[str, Any]],
    diagnostics_by_run: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    metric_names = [
        "global_concurrency_wait_seconds",
        "per_tool_concurrency_wait_seconds",
        "global_rate_wait_seconds",
        "per_tool_rate_wait_seconds",
        "max_inflight_global",
        "total_rate_limited_attempts",
    ]
    per_run_rows: List[Dict[str, Any]] = []
    metric_values: Dict[str, List[float]] = {name: [] for name in metric_names}

    for run in runs:
        run_id = run["run_id"]
        diagnostics = diagnostics_by_run.get(run_id, {})
        payload = diagnostics.get("payload", {})
        saturation = payload.get("saturation_metrics") if isinstance(payload, dict) else {}
        saturation = saturation if isinstance(saturation, dict) else {}
        row = {
            "run_id": run_id,
            "completed_at_utc": run["completed_at_utc"],
            "failed_steps": run["failed_steps"],
            "metrics": {},
        }
        for name in metric_names:
            value = saturation.get(name, 0.0)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 0.0
            row["metrics"][name] = round(numeric, 6)
            metric_values[name].append(numeric)
        per_run_rows.append(row)

    aggregate = {
        name: _aggregate_numeric(values)
        for name, values in metric_values.items()
    }
    return {"aggregate": aggregate, "per_run": per_run_rows[:100]}


def _build_actor_view(
    runs: Sequence[Dict[str, Any]],
    diagnostics_by_run: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    owner_counts: Dict[str, int] = {}
    last_actor_counts: Dict[str, int] = {}
    operation_counts: Dict[str, int] = {}
    run_actor_rows: List[Dict[str, Any]] = []

    for run in runs:
        run_id = run["run_id"]
        diagnostics = diagnostics_by_run.get(run_id, {})
        payload = diagnostics.get("payload", {})
        actor_metadata = payload.get("actor_metadata") if isinstance(payload, dict) else {}
        actor_metadata = actor_metadata if isinstance(actor_metadata, dict) else {}

        owner_actor_id = actor_metadata.get("owner_actor_id")
        last_actor_id = actor_metadata.get("actor_id")
        operation = actor_metadata.get("operation")

        if isinstance(owner_actor_id, str) and owner_actor_id:
            owner_counts[owner_actor_id] = owner_counts.get(owner_actor_id, 0) + 1
        if isinstance(last_actor_id, str) and last_actor_id:
            last_actor_counts[last_actor_id] = last_actor_counts.get(last_actor_id, 0) + 1
        if isinstance(operation, str) and operation:
            operation_counts[operation] = operation_counts.get(operation, 0) + 1

        run_actor_rows.append(
            {
                "run_id": run_id,
                "owner_actor_id": owner_actor_id,
                "actor_id": last_actor_id,
                "operation": operation,
                "actor_scopes": actor_metadata.get("actor_scopes") or [],
            }
        )

    return {
        "owner_actor_counts": owner_counts,
        "last_actor_counts": last_actor_counts,
        "operation_counts": operation_counts,
        "per_run": run_actor_rows[:100],
    }


def _select_failed_run(
    runs: Sequence[Dict[str, Any]],
    requested_run_id: Optional[str] = None,
) -> Optional[str]:
    if requested_run_id:
        for run in runs:
            if run["run_id"] == requested_run_id:
                return requested_run_id
        return None
    for run in runs:
        if run["failed_steps"] > 0:
            return run["run_id"]
    return None


def _build_failed_run_diagnostics(
    runs: Sequence[Dict[str, Any]],
    trace_rows: Sequence[Dict[str, Any]],
    diagnostics_by_run: Dict[str, Dict[str, Any]],
    failed_run_id: Optional[str],
) -> Dict[str, Any]:
    if not failed_run_id:
        return {
            "failed_run_id": None,
            "message": "No failed runs found in selected window.",
            "timeline": [],
            "root_failure": None,
            "dependency_cascade_count": 0,
        }

    run_row = next((run for run in runs if run["run_id"] == failed_run_id), None)
    run_trace = [row for row in trace_rows if row["run_id"] == failed_run_id]
    failed_events = [row for row in run_trace if row["event_type"] == "failed"]

    root_failure = None
    for event in failed_events:
        error_type = (event.get("error_payload") or {}).get("error_type")
        if error_type and error_type != "dependency_error":
            root_failure = event
            break
    if root_failure is None and failed_events:
        root_failure = failed_events[0]

    dependency_cascade_count = 0
    for event in failed_events:
        error_type = (event.get("error_payload") or {}).get("error_type")
        if error_type == "dependency_error":
            dependency_cascade_count += 1

    timeline = []
    for event in run_trace:
        error_payload = event.get("error_payload") or {}
        timeline.append(
            {
                "timestamp_utc": event["timestamp_utc"],
                "step_id": event["step_id"],
                "tool_name": event["tool_name"],
                "event_type": event["event_type"],
                "attempt": event["attempt"],
                "duration_ms": event["duration_ms"],
                "error_type": error_payload.get("error_type"),
                "message": error_payload.get("message"),
            }
        )

    root_failure_payload = None
    if root_failure is not None:
        error_payload = root_failure.get("error_payload") or {}
        root_failure_payload = {
            "run_id": root_failure["run_id"],
            "step_id": root_failure["step_id"],
            "tool_name": root_failure["tool_name"],
            "timestamp_utc": root_failure["timestamp_utc"],
            "error_type": error_payload.get("error_type"),
            "message": error_payload.get("message"),
        }

    diagnostics_payload = diagnostics_by_run.get(failed_run_id, {}).get("payload", {})
    actor_metadata = (
        diagnostics_payload.get("actor_metadata")
        if isinstance(diagnostics_payload, dict)
        else {}
    )
    actor_metadata = actor_metadata if isinstance(actor_metadata, dict) else {}
    return {
        "failed_run_id": failed_run_id,
        "run_summary": run_row,
        "actor_metadata": actor_metadata,
        "root_failure": root_failure_payload,
        "dependency_cascade_count": dependency_cascade_count,
        "timeline": timeline,
        "run_diagnostics": diagnostics_payload,
    }


def _build_overview(
    runs: Sequence[Dict[str, Any]],
    retries_view: Dict[str, Any],
    fail_reasons_view: Dict[str, Any],
    latency_view: Dict[str, Any],
    saturation_view: Dict[str, Any],
    actor_view: Dict[str, Any],
) -> Dict[str, Any]:
    run_count = len(runs)
    failed_run_count = sum(1 for run in runs if run["failed_steps"] > 0)
    failure_rate = (float(failed_run_count) / float(run_count)) if run_count else 0.0
    return {
        "run_count": run_count,
        "failed_run_count": failed_run_count,
        "failed_run_rate": round(failure_rate, 6),
        "retry_event_total": retries_view["retry_event_total"],
        "failed_event_total": fail_reasons_view["failed_event_total"],
        "latency": latency_view["overall"],
        "saturation": saturation_view["aggregate"],
        "actors": {
            "owner_actor_counts": actor_view.get("owner_actor_counts", {}),
            "last_actor_counts": actor_view.get("last_actor_counts", {}),
            "operation_counts": actor_view.get("operation_counts", {}),
        },
    }


def _recommendations_for_failure(diagnostics: Dict[str, Any]) -> List[str]:
    root = diagnostics.get("root_failure") or {}
    error_type = root.get("error_type")
    recommendations: List[str] = []
    if error_type == "tool_execution_error":
        recommendations.append("Inspect failing tool inputs and upstream payload quality for the root failure step.")
        recommendations.append("Adjust RetryPolicy.retryable_error_types if the failure is transient and currently non-retryable.")
    elif error_type == "dependency_error":
        recommendations.append("Trace upstream failing step and repair its tool contract before retrying downstream steps.")
    elif error_type == "approval_rejected":
        recommendations.append("Check approval workflow policy and rejection reason for the blocked step.")
    else:
        recommendations.append("Review root failure event payload and correlated step trace to isolate first error.")
    if diagnostics.get("dependency_cascade_count", 0) > 0:
        recommendations.append("Dependency cascade detected; prioritize fixing the first non-dependency failure event.")
    return recommendations


def _render_markdown_report(
    overview: Dict[str, Any],
    retries_view: Dict[str, Any],
    fail_reasons_view: Dict[str, Any],
    failed_run_diagnostics: Dict[str, Any],
) -> str:
    lines = [
        "# Operator Telemetry Pack",
        "",
        f"- Generated: `{_now_utc_iso()}`",
        f"- Runs analyzed: `{overview['run_count']}`",
        f"- Failed runs: `{overview['failed_run_count']}` (`{overview['failed_run_rate']:.2%}`)",
        f"- Retry events: `{overview['retry_event_total']}`",
        "",
        "## High-Level Signals",
        "",
        f"- Top failure types: `{fail_reasons_view.get('error_type_counts', {})}`",
        f"- Top retry tools: `{retries_view.get('by_tool', [])[:5]}`",
        f"- Step latency p95 (ms): `{overview['latency'].get('p95', 0.0):.3f}`",
        f"- Global rate-wait p95 (s): "
        f"`{overview['saturation'].get('global_rate_wait_seconds', {}).get('p95', 0.0):.6f}`",
        "",
        "## Failed Run Diagnosis",
        "",
    ]

    failed_run_id = failed_run_diagnostics.get("failed_run_id")
    if not failed_run_id:
        lines.append("- No failed runs were found in the selected window.")
        return "\n".join(lines) + "\n"

    root = failed_run_diagnostics.get("root_failure") or {}
    actor_metadata = failed_run_diagnostics.get("actor_metadata") or {}
    lines.append(f"- Failed run: `{failed_run_id}`")
    if actor_metadata:
        lines.append(
            f"- Owner actor: `{actor_metadata.get('owner_actor_id', 'unknown')}` | "
            f"Last actor: `{actor_metadata.get('actor_id', 'unknown')}` | "
            f"Operation: `{actor_metadata.get('operation', 'unknown')}`"
        )
    lines.append(
        f"- Root failure: `{root.get('error_type', 'unknown')}` in `{root.get('tool_name', 'unknown')}`/"
        f"`{root.get('step_id', 'unknown')}`"
    )
    if root.get("message"):
        lines.append(f"- Root message: `{root['message']}`")
    lines.append(
        f"- Dependency cascade events: `{failed_run_diagnostics.get('dependency_cascade_count', 0)}`"
    )
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    for action in _recommendations_for_failure(failed_run_diagnostics):
        lines.append(f"- {action}")
    lines.append("")
    lines.append("## Timeline Snapshot")
    lines.append("")
    timeline = failed_run_diagnostics.get("timeline", [])[:12]
    if not timeline:
        lines.append("- No timeline events captured.")
    else:
        for event in timeline:
            lines.append(
                f"- `{event.get('timestamp_utc')}` `{event.get('event_type')}` "
                f"`{event.get('tool_name')}/{event.get('step_id')}` "
                f"(attempt {event.get('attempt')})"
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export dashboard-ready telemetry artifacts for EAP operations.")
    parser.add_argument("--db-path", default="agent_state.db", help="Path to SQLite state database.")
    parser.add_argument(
        "--output-dir",
        default="artifacts/telemetry",
        help="Directory where telemetry artifacts are written.",
    )
    parser.add_argument(
        "--limit-runs",
        type=int,
        default=500,
        help="Maximum number of recent runs to include.",
    )
    parser.add_argument(
        "--failed-run-id",
        default=None,
        help="Optional specific failed run ID for diagnosis drilldown.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(args.db_path) as conn:
        runs = _load_runs(conn, limit=args.limit_runs)
        run_ids = [run["run_id"] for run in runs]
        trace_rows = _load_trace_rows(conn, run_ids=run_ids)
        diagnostics_by_run = _load_diagnostics(conn, run_ids=run_ids)

    retries_view = _build_retries_view(trace_rows)
    fail_reasons_view = _build_fail_reasons_view(trace_rows)
    latency_view = _build_latency_view(trace_rows)
    saturation_view = _build_saturation_view(runs, diagnostics_by_run=diagnostics_by_run)
    actor_view = _build_actor_view(runs, diagnostics_by_run=diagnostics_by_run)
    failed_run_id = _select_failed_run(runs, requested_run_id=args.failed_run_id)
    failed_run_diagnostics = _build_failed_run_diagnostics(
        runs=runs,
        trace_rows=trace_rows,
        diagnostics_by_run=diagnostics_by_run,
        failed_run_id=failed_run_id,
    )
    overview = _build_overview(
        runs=runs,
        retries_view=retries_view,
        fail_reasons_view=fail_reasons_view,
        latency_view=latency_view,
        saturation_view=saturation_view,
        actor_view=actor_view,
    )

    outputs = {
        "overview.json": overview,
        "retries.json": retries_view,
        "fail_reasons.json": fail_reasons_view,
        "latency_percentiles.json": latency_view,
        "saturation.json": saturation_view,
        "actors.json": actor_view,
        "failed_run_diagnostics.json": failed_run_diagnostics,
    }
    for filename, payload in outputs.items():
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    report = _render_markdown_report(
        overview=overview,
        retries_view=retries_view,
        fail_reasons_view=fail_reasons_view,
        failed_run_diagnostics=failed_run_diagnostics,
    )
    (output_dir / "operator_report.md").write_text(report, encoding="utf-8")

    manifest = {
        "generated_at_utc": _now_utc_iso(),
        "db_path": str(Path(args.db_path).resolve()),
        "output_dir": str(output_dir.resolve()),
        "files": sorted(
            [path.name for path in output_dir.iterdir() if path.is_file()] + ["manifest.json"]
        ),
        "failed_run_id": failed_run_id,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
