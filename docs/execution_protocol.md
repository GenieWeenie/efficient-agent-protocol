# Execution Protocol (Linear-First)

This protocol prevents ad-hoc execution and keeps all work in a visible ordered queue.

## Source Of Truth

1. Linear issue state is the execution authority.
2. This file mirrors the active order (`Now`, `Next`, `Blocked`).
3. `docs/phase7_competitive_openclaw_roadmap.md` and `docs/phase8_adoption_limits_closure_roadmap.md` are narrative roadmaps, not the live queue.

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

Updated: 2026-02-24

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

## Execution Rule

Do not start a new implementation item unless it is the first non-blocked `Todo` item in this queue.  
Current state: no `Todo` items remain in the tracked queue.
