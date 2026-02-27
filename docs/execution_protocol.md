# Execution Protocol (Linear-First)

This protocol prevents ad-hoc execution and keeps all work in a visible ordered queue.

## Source Of Truth

1. Linear issue state is the execution authority.
2. This file mirrors the active order (`Now`, `Next`, `Blocked`).
3. `docs/phase7_competitive_openclaw_roadmap.md`, `docs/phase8_adoption_limits_closure_roadmap.md`, `docs/phase9_production_readiness_roadmap.md`, and `docs/phase10_competitiveness_hardening_roadmap.md` are narrative roadmaps, not the live queue.

## Start Gate (Must Be True Before Coding)

1. Issue exists in Linear with an EAP ID.
2. Issue has explicit deliverable + measurable done criteria.
3. Issue state is `Todo` and it is the top `Next` item.
4. Dependencies are either `Done` or explicitly marked as blockers.

## Finish Gate (Must Be True Before Marking Done)

1. Code/docs/tests merged to `main`.
2. Required CI checks pass.
3. Roadmap/docs updated for status and next item.
4. Linear issue moved to `Done` with merged PR link.

## Current Ordered Queue

Updated: 2026-02-26 (v0.1.8 baseline)

| Order | EAP ID | Linear | Status | Notes |
| --- | --- | --- | --- | --- |
| 1 | `EAP-084` | `GEN-45` | `Done` | Establish execution protocol + queue mirror |
| 2 | `EAP-085` | `GEN-44` | `Done` | Tranche 4 scope and acceptance criteria defined |
| 3 | `EAP-086` | `GEN-46` | `Done` | OpenClaw agent-routing header support |
| 4 | `EAP-087` | `GEN-48` | `Done` | OpenClaw `/tools/invoke` bridge |
| 5 | `EAP-088` | `GEN-47` | `Done` | OpenAI Responses API adapter path |
| 6 | `EAP-089` | `GEN-49` | `Done` | Responses streaming parity |
| 7 | `EAP-090` | `GEN-50` | `Done` | v1 compatibility enforcement |
| 8 | `EAP-091` | `GEN-51` | `Done` | One-command bootstrap |
| 9 | `EAP-092` | `GEN-52` | `Done` | Guided onboarding + doctor |
| 10 | `EAP-093` | `GEN-53` | `Done` | Self-hosted control-plane reference |
| 11 | `EAP-094` | `GEN-54` | `Done` | Remote operations governance baseline |
| 12 | `EAP-095` | `GEN-55` | `Done` | Runtime policy profile packs + deny-by-default templates |
| 13 | `EAP-096` | `GEN-56` | `Done` | Runtime rate limits and concurrency guards |
| 14 | `EAP-097` | `GEN-57` | `Done` | Audit log export + signed integrity manifest |
| 15 | `EAP-100` | `GEN-60` | `Done` | Reproducible benchmark + competitor comparison suite |
| 16 | `EAP-101` | `GEN-61` | `Done` | Docs deepening: custom tools, pointer internals, architecture completeness |
| 17 | `EAP-102` | `GEN-62` | `Done` | Security hardening for expression evaluation paths |
| 18 | `EAP-103` | `GEN-63` | `Done` | README conversion pack (demo GIF, architecture prominence, badges hygiene) |
| 19 | `EAP-104` | `GEN-64` | `Done` | Type rigor tranche (mypy scope + stricter typing checks) |
| 20 | `EAP-098` | `GEN-58` | `Done` | Backup/restore workflow for state + diagnostics |
| 21 | `EAP-099` | `GEN-59` | `Done` | Long-run soak + chaos reliability gate |
| 22 | `EAP-109` | `GEN-65` | `Done` | Strict typing tranche: executor runtime path (`environment/executor.py`) |
| 23 | `EAP-110` | `GEN-66` | `Done` | Strict typing tranche: runtime HTTP API path (`eap/runtime/http_api.py`) |
| 24 | `EAP-111` | `GEN-67` | `Todo` | Freeze pointer lifecycle semantics for v1 (`TTL/expiry/cleanup`) |
| 25 | `EAP-112` | `GEN-68` | `Todo` | Public API deprecation sweep + unstable export cleanup |
| 26 | `EAP-113` | `GEN-69` | `Todo` | Upgrade migration verification from latest `0.x` baseline |
| 27 | `EAP-114` | `GEN-70` | `Todo` | Observability compatibility lock (logs/metrics/telemetry schema) |
| 28 | `EAP-115` | `GEN-71` | `Todo` | V1 readiness gatepack (coverage/perf/reliability/security) |
| 29 | `EAP-116` | `GEN-72` | `Todo` | README/docs v1 alignment pass |
| 30 | `EAP-117` | `GEN-73` | `Todo` | Release + maintainer runbook v1 finalization |
| 31 | `EAP-118` | `GEN-74` | `Todo` | V1 upgrade handoff artifact + RC dry-run |

## Execution Rule

Do not start a new implementation item unless it is the first non-blocked `Todo` item in this queue.  
Current state: next queued `Todo` item is `EAP-111`; extended queued backlog is defined through `EAP-118`.
