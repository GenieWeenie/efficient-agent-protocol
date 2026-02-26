# Soak + Chaos Reliability Gate (EAP-099)

This harness adds a CI-gated reliability proof for sustained load plus injected faults.

## Command

```bash
python scripts/soak_chaos_scorecard.py \
  --output-dir artifacts/soak_chaos \
  --threshold-config docs/soak_chaos_thresholds.json \
  --baseline docs/soak_chaos_baseline.json
```

## What It Measures

1. Soak flow:
   - repeated runtime macro execution over a configurable number of runs.
   - deterministic transient timeout injection every N runs to verify retry behavior under sustained load.
   - pass/failure rate, retry-event volume, and latency (`p50`, `p95`, `max`).
2. Chaos scenarios:
   - `dependency_outage`: upstream outage should propagate downstream dependency failure deterministically.
   - `timeout_recovery`: transient timeout should recover through retry policy.
   - `retry_storm`: repeated timeout bursts should remain recoverable with bounded retries.

## Regression Gates

Configured in `docs/soak_chaos_thresholds.json`, including:

- minimum soak run count
- maximum soak failure rate
- maximum soak latency p95
- minimum retry evidence during soak and chaos
- minimum chaos pass rate + required scenarios
- baseline-relative regression checks from `docs/soak_chaos_baseline.json`

The script exits non-zero when the gate fails.

## Artifacts

Written to `artifacts/soak_chaos/`:

- `scorecard.json`: full machine-readable results and gate evaluation
- `scorecard.md`: concise human summary
- `trend.json`: current vs baseline deltas
- `history.ndjson`: append-only local run history

CI uploads this directory as the `soak-chaos-reliability` artifact.

## Interpretation Guidance

- High soak `failure_rate` with low retry events:
  - likely non-retryable failures or dependency instability.
  - inspect runtime trace events and error types first.
- High soak `latency_ms.p95` with stable pass rate:
  - likely saturation or throttling pressure.
  - inspect diagnostics saturation metrics from run metadata.
- Chaos scenario failures:
  - `dependency_outage` fail usually indicates dependency error propagation drift.
  - `timeout_recovery` fail indicates retry policy mismatch/regression.
  - `retry_storm` fail indicates retry/backoff behavior no longer stable under burst faults.

## Remediation Flow

1. Open `artifacts/soak_chaos/scorecard.json` and list exact gate failures.
2. Re-run locally with a fixed seed/config and capture traces.
3. Classify failure:
   - dependency behavior regression
   - retry policy regression
   - latency/saturation regression
4. Patch behavior and add/adjust targeted tests to lock the fix.
5. Re-run `scripts/soak_chaos_scorecard.py` until gate passes.
6. If baseline is outdated and performance is intentionally improved/changed, update baseline in a dedicated PR with evidence.
