# Benchmarks

This document defines the reproducible benchmark method for EAP and records baseline numbers.

## Environment

Capture and publish this context alongside benchmark results:

- OS and version
- CPU model
- Python version
- EAP commit SHA
- whether debug/profiling instrumentation is enabled

## Benchmark Command

Run the performance test subset:

```bash
python3 -m pytest -q tests/perf --durations=10
```

Run the Phase 7 scorecard harness (correctness + reliability + latency):

```bash
python scripts/eval_scorecard.py \
  --output-dir artifacts/eval \
  --threshold-config docs/eval_thresholds.json \
  --baseline docs/eval_baseline.json
```

## Baseline (2026-02-23)

Measured on local macOS development machine, Python 3.9:

- `tests/perf/test_concurrency_limits.py::ConcurrencyLimitsPerfTest::test_rate_limit_generates_saturation_metrics`: `1.70s`
- `tests/perf/test_concurrency_limits.py::ConcurrencyLimitsPerfTest::test_global_concurrency_limit_caps_parallel_work`: `0.28s`
- `tests/perf/test_distributed_resilience.py::DistributedResiliencePerfTest::test_expired_lease_is_reassigned`: `0.01s`
- `tests/perf/test_distributed_resilience.py::DistributedResiliencePerfTest::test_stale_completion_report_is_rejected_after_reassignment`: `0.01s`

## CI Regression Gates

Critical perf tests include upper-bound assertions to catch major slowdowns:

- global-concurrency perf test: must stay below `2.0s`
- rate-limit perf test: must stay below `4.0s`

These assertions run in standard CI test jobs.
