#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _run_eval_scorecard(
    *,
    eval_output_dir: Path,
    eval_threshold_config: Path,
    eval_baseline: Path,
    latency_iterations: int,
) -> Path:
    eval_output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "eval_scorecard.py"),
        "--output-dir",
        str(eval_output_dir),
        "--threshold-config",
        str(eval_threshold_config),
        "--baseline",
        str(eval_baseline),
        "--latency-iterations",
        str(latency_iterations),
    ]
    completed = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "eval_scorecard.py failed before competitive benchmark comparison:\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}"
        )
    return eval_output_dir / "scorecard.json"


def _extract_workflow_rows(scorecard: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for section in ("correctness", "reliability"):
        for scenario in scorecard.get(section, {}).get("scenarios", []):
            name = str(scenario.get("name", "")).strip()
            if not name:
                continue
            rows[name] = {
                "name": name,
                "passed": bool(scenario.get("passed", False)),
                "duration_ms": float(scenario.get("duration_ms", 0.0)),
                "section": section,
            }
    return rows


def _build_comparison(
    *,
    scorecard: Dict[str, Any],
    profiles: Dict[str, Any],
    thresholds: Dict[str, Any],
) -> Dict[str, Any]:
    eap_metrics = {
        "correctness_pass_rate": float(scorecard["correctness"]["pass_rate"]),
        "reliability_pass_rate": float(scorecard["reliability"]["pass_rate"]),
        "latency_p95_ms": float(scorecard["latency_ms"]["p95"]),
        "latency_max_ms": float(scorecard["latency_ms"]["max"]),
    }
    workflow_rows = _extract_workflow_rows(scorecard)
    selected_workflows = [str(name) for name in profiles.get("selected_workflows", [])]
    reference_profiles = profiles.get("reference_profiles", [])

    matrix_rows: List[Dict[str, Any]] = []
    for profile in reference_profiles:
        profile_metrics = profile.get("metrics", {})
        row = {
            "id": profile.get("id"),
            "display_name": profile.get("display_name"),
            "provenance": profile.get("provenance"),
            "metrics": profile_metrics,
            "delta_vs_eap": {
                "correctness_pass_rate": round(
                    eap_metrics["correctness_pass_rate"] - float(profile_metrics.get("correctness_pass_rate", 0.0)),
                    6,
                ),
                "reliability_pass_rate": round(
                    eap_metrics["reliability_pass_rate"] - float(profile_metrics.get("reliability_pass_rate", 0.0)),
                    6,
                ),
                "latency_p95_ms": round(
                    eap_metrics["latency_p95_ms"] - float(profile_metrics.get("latency_p95_ms", 0.0)),
                    6,
                ),
            },
            "workflow_comparison": [],
        }
        profile_workflows = profile.get("workflow_pass_rates", {})
        for workflow_name in selected_workflows:
            eap_workflow = workflow_rows.get(workflow_name)
            if eap_workflow is None:
                eap_pass_rate = None
                eap_duration_ms = None
            else:
                eap_pass_rate = 1.0 if eap_workflow["passed"] else 0.0
                eap_duration_ms = eap_workflow["duration_ms"]
            profile_pass_rate = profile_workflows.get(workflow_name)
            row["workflow_comparison"].append(
                {
                    "workflow": workflow_name,
                    "eap_pass_rate": eap_pass_rate,
                    "eap_duration_ms": eap_duration_ms,
                    "reference_pass_rate": profile_pass_rate,
                    "pass_rate_delta": (
                        None
                        if eap_pass_rate is None or profile_pass_rate is None
                        else round(float(eap_pass_rate) - float(profile_pass_rate), 6)
                    ),
                }
            )
        matrix_rows.append(row)

    gate_failures: List[str] = []
    metrics_gate = thresholds.get("metrics", {})
    advantage_gate = thresholds.get("advantage", {})
    required_profiles = int(thresholds.get("required_reference_profiles", 0))
    min_correctness = float(metrics_gate.get("min_correctness_pass_rate", 0.0))
    min_reliability = float(metrics_gate.get("min_reliability_pass_rate", 0.0))
    max_latency_p95 = float(metrics_gate.get("max_latency_p95_ms", float("inf")))
    min_correctness_delta = float(advantage_gate.get("min_correctness_delta", 0.0))
    min_reliability_delta = float(advantage_gate.get("min_reliability_delta", 0.0))

    if len(reference_profiles) < required_profiles:
        gate_failures.append(
            f"reference profile count {len(reference_profiles)} below required {required_profiles}"
        )
    if eap_metrics["correctness_pass_rate"] < min_correctness:
        gate_failures.append(
            "eap correctness pass rate below threshold: "
            f"{eap_metrics['correctness_pass_rate']:.3f} < {min_correctness:.3f}"
        )
    if eap_metrics["reliability_pass_rate"] < min_reliability:
        gate_failures.append(
            "eap reliability pass rate below threshold: "
            f"{eap_metrics['reliability_pass_rate']:.3f} < {min_reliability:.3f}"
        )
    if eap_metrics["latency_p95_ms"] > max_latency_p95:
        gate_failures.append(
            "eap latency p95 above threshold: "
            f"{eap_metrics['latency_p95_ms']:.3f} > {max_latency_p95:.3f}"
        )
    for workflow_name in selected_workflows:
        if workflow_name not in workflow_rows:
            gate_failures.append(f"missing workflow result in eval scorecard: {workflow_name}")

    for row in matrix_rows:
        correctness_delta = float(row["delta_vs_eap"]["correctness_pass_rate"])
        reliability_delta = float(row["delta_vs_eap"]["reliability_pass_rate"])
        if correctness_delta < min_correctness_delta:
            gate_failures.append(
                f"correctness delta vs {row['id']} below required minimum: "
                f"{correctness_delta:.3f} < {min_correctness_delta:.3f}"
            )
        if reliability_delta < min_reliability_delta:
            gate_failures.append(
                f"reliability delta vs {row['id']} below required minimum: "
                f"{reliability_delta:.3f} < {min_reliability_delta:.3f}"
            )

    return {
        "generated_at_utc": _now_utc_iso(),
        "schema_version": "1.0",
        "source_eval_generated_at_utc": scorecard.get("generated_at_utc"),
        "selected_workflows": selected_workflows,
        "reference_profile_count": len(reference_profiles),
        "eap_metrics": eap_metrics,
        "reference_matrix": matrix_rows,
        "gate": {
            "passed": len(gate_failures) == 0,
            "failures": gate_failures,
            "thresholds": thresholds,
        },
    }


def _render_markdown(scorecard: Dict[str, Any], profiles_path: Path) -> str:
    gate_status = "PASS" if scorecard["gate"]["passed"] else "FAIL"
    lines = [
        "# Competitive Benchmark Scorecard",
        "",
        f"- Generated: `{scorecard['generated_at_utc']}`",
        f"- Source eval generated: `{scorecard['source_eval_generated_at_utc']}`",
        f"- Reference profiles: `{profiles_path}`",
        f"- Gate: **{gate_status}**",
        "",
        "## EAP Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Correctness pass rate | `{scorecard['eap_metrics']['correctness_pass_rate']:.3f}` |",
        f"| Reliability pass rate | `{scorecard['eap_metrics']['reliability_pass_rate']:.3f}` |",
        f"| Latency p95 (ms) | `{scorecard['eap_metrics']['latency_p95_ms']:.3f}` |",
        f"| Latency max (ms) | `{scorecard['eap_metrics']['latency_max_ms']:.3f}` |",
        "",
        "## Comparison Matrix",
        "",
        "| Profile | Correctness Δ (EAP-profile) | Reliability Δ (EAP-profile) | Latency p95 Δ ms (EAP-profile) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in scorecard["reference_matrix"]:
        lines.append(
            f"| {row['display_name']} | "
            f"`{row['delta_vs_eap']['correctness_pass_rate']:.3f}` | "
            f"`{row['delta_vs_eap']['reliability_pass_rate']:.3f}` | "
            f"`{row['delta_vs_eap']['latency_p95_ms']:.3f}` |"
        )
    lines.extend(["", "## Gate Result", ""])
    failures = scorecard["gate"]["failures"]
    if failures:
        for failure in failures:
            lines.append(f"- [ ] {failure}")
    else:
        lines.append("- [x] Competitive benchmark thresholds satisfied.")
    lines.extend(
        [
            "",
            "## Methodology Note",
            "",
            "- Reference profiles are explicit fixture baselines for reproducible comparison, not live vendor benchmarks.",
            "- Re-run command and fixture sources are documented in `docs/benchmarks.md`.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reproducible EAP-vs-reference competitive benchmark scorecard."
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/competitive_benchmarks",
        help="Directory for competitive benchmark artifacts.",
    )
    parser.add_argument(
        "--profiles",
        default=str(REPO_ROOT / "docs" / "competitive_reference_profiles.json"),
        help="Reference profile fixture JSON path.",
    )
    parser.add_argument(
        "--threshold-config",
        default=str(REPO_ROOT / "docs" / "competitive_thresholds.json"),
        help="Competitive benchmark gate threshold config JSON path.",
    )
    parser.add_argument(
        "--eval-scorecard",
        default=None,
        help="Optional existing eval scorecard JSON path. When omitted, eval scorecard is generated.",
    )
    parser.add_argument(
        "--eval-threshold-config",
        default=str(REPO_ROOT / "docs" / "eval_thresholds.json"),
        help="Threshold config used when generating eval scorecard.",
    )
    parser.add_argument(
        "--eval-baseline",
        default=str(REPO_ROOT / "docs" / "eval_baseline.json"),
        help="Baseline used when generating eval scorecard.",
    )
    parser.add_argument(
        "--latency-iterations",
        type=int,
        default=12,
        help="Latency iterations when generating eval scorecard.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profiles_path = Path(args.profiles)
    thresholds_path = Path(args.threshold_config)

    if args.eval_scorecard:
        eval_scorecard_path = Path(args.eval_scorecard)
    else:
        eval_output_dir = output_dir / "eval"
        eval_scorecard_path = _run_eval_scorecard(
            eval_output_dir=eval_output_dir,
            eval_threshold_config=Path(args.eval_threshold_config),
            eval_baseline=Path(args.eval_baseline),
            latency_iterations=args.latency_iterations,
        )

    scorecard = _load_json(eval_scorecard_path)
    profiles = _load_json(profiles_path)
    thresholds = _load_json(thresholds_path)
    comparison = _build_comparison(scorecard=scorecard, profiles=profiles, thresholds=thresholds)

    _write_json(output_dir / "comparison_scorecard.json", comparison)
    (output_dir / "comparison_scorecard.md").write_text(
        _render_markdown(comparison, profiles_path=profiles_path),
        encoding="utf-8",
    )
    _write_json(
        output_dir / "manifest.json",
        {
            "generated_at_utc": _now_utc_iso(),
            "profiles_path": str(profiles_path.resolve()),
            "threshold_config_path": str(thresholds_path.resolve()),
            "eval_scorecard_path": str(eval_scorecard_path.resolve()),
            "artifacts": sorted([p.name for p in output_dir.iterdir() if p.is_file()]),
            "gate_passed": comparison["gate"]["passed"],
        },
    )

    print(
        json.dumps(
            {
                "gate_passed": comparison["gate"]["passed"],
                "failures": comparison["gate"]["failures"],
                "output_dir": str(output_dir.resolve()),
                "scorecard_file": str((output_dir / "comparison_scorecard.json").resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if comparison["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
