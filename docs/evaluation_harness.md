# Evaluation Harness and Scorecard (EAP-079)

This harness provides a repeatable CI-gated evaluation suite for:

- correctness
- reliability
- latency

It emits machine-readable and human-readable artifacts for trend tracking.

## Command

```bash
python scripts/eval_scorecard.py \
  --output-dir artifacts/eval \
  --threshold-config docs/eval_thresholds.json \
  --baseline docs/eval_baseline.json
```

## What It Measures

1. Correctness:
   - Reference multi-step flow output integrity.
2. Reliability:
   - Retry recovery for transient timeout errors.
   - Dependency failure propagation semantics.
3. Latency:
   - Repeated single-step runtime execution latency (`p50`, `p95`, `max`).

## Regression Gates

Thresholds are configured in `docs/eval_thresholds.json`.

Gate rules include:
- minimum correctness pass rate
- minimum reliability pass rate
- absolute latency ceilings
- baseline-relative regression limits (from `docs/eval_baseline.json`)

The harness exits non-zero when any gate fails.

## Artifacts

The harness writes to `artifacts/eval/`:

- `scorecard.json`: full structured output (inputs, scenario results, gate)
- `scorecard.md`: concise human summary
- `trend.json`: baseline vs current deltas for key metrics
- `history.ndjson`: append-only run records for local trend aggregation

CI uploads `artifacts/eval/` as the `eval-scorecard` artifact on every run.

## Competitive Comparison Layer (EAP-100)

After `scorecard.json` is produced, run:

```bash
python scripts/competitive_benchmark_suite.py \
  --output-dir artifacts/competitive_benchmarks \
  --eval-scorecard artifacts/eval/scorecard.json \
  --profiles docs/competitive_reference_profiles.json \
  --threshold-config docs/competitive_thresholds.json
```

This layer generates a reproducible comparison matrix against versioned reference profiles and applies an additional threshold gate.
