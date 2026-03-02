# SLO / SLA Guidance

Recommendations for setting Service Level Objectives and Agreements for EAP deployments.

## Golden Signals

EAP operators should monitor four golden signals:

| Signal | Metric | Source |
|---|---|---|
| **Latency** | Step execution duration (p50, p95, p99) | `latency_percentiles.json` via telemetry pack |
| **Error Rate** | Failed runs / total runs | `overview.json` → `failed_run_rate` |
| **Saturation** | Concurrency wait time, rate-limit wait time | `saturation.json` |
| **Traffic** | Runs per minute, trace events per minute | `overview.json` → `run_count` |

## Example SLO Definitions

### Latency SLO

**Objective**: 95% of step executions complete within 500ms (excluding external API calls).

```
Threshold: latency_percentiles.overall.p95 < 500.0 ms
Measurement window: Rolling 1 hour
Alert: Fire when p95 exceeds 500ms for 3 consecutive windows
```

### Availability SLO

**Objective**: 99% of macro executions complete without infrastructure failures.

```
Threshold: (1 - failed_run_rate) >= 0.99
Measurement window: Rolling 24 hours
Exclude: Intentional tool failures (user logic errors)
Alert: Fire when availability drops below 99% for 2 consecutive windows
```

### Error Budget

For a 99% availability target over 30 days:
- **Budget**: 7.2 hours of allowed downtime / failure
- **Burn rate alert**: Fire when errors consume > 5% of monthly budget in 1 hour

## Setting Up Alerts

### With Prometheus + Alertmanager

Use the metrics exported by `export_telemetry_pack.py` to feed a Prometheus-compatible endpoint:

```yaml
# Example Prometheus alerting rule
groups:
  - name: eap_slo
    rules:
      - alert: EAPHighLatency
        expr: eap_step_latency_p95_ms > 500
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "EAP step latency p95 exceeds 500ms"

      - alert: EAPHighErrorRate
        expr: eap_failed_run_rate > 0.01
        for: 30m
        labels:
          severity: critical
        annotations:
          summary: "EAP failed run rate exceeds 1%"
```

### With JSON Quick Views

For teams without Prometheus, use the telemetry pack JSON files directly:

1. Run `python scripts/export_telemetry_pack.py --verbose` on a schedule (cron / systemd timer)
2. Parse `overview.json` for `failed_run_rate` and `latency.p95`
3. Parse `saturation.json` for concurrency/rate-limit wait times
4. Alert via webhook / email when thresholds breach

## Tuning Thresholds

Start with conservative thresholds and tighten as you collect baseline data:

| Metric | Starting Threshold | Tightened Threshold |
|---|---|---|
| Latency p95 | 1000ms | 500ms |
| Error rate | 5% | 1% |
| Global concurrency wait p95 | 5s | 1s |
| Rate-limit retries/hour | 100 | 20 |

See `docs/eval_thresholds.json` for CI gate thresholds and `docs/soak_chaos_thresholds.json` for reliability thresholds.
