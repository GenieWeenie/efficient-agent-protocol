# Phase 7 Tranche 4 Scope (EAP-085)

Updated: 2026-02-24  
Source of truth: Linear project `Efficient Agent Protocol Roadmap`

## Objective

Close the remaining high-impact OpenClaw interoperability gaps identified in `docs/openclaw_interop.md` section 3.

## Ordered Implementation Items

| Order | EAP ID | Linear | Scope | Deliverable | Done Criteria |
| --- | --- | --- | --- | --- | --- |
| 1 | `EAP-086` | `GEN-46` | OpenClaw agent routing header support | Configurable extra headers in `OpenAIProvider`, including `x-openclaw-agent-id` path | Header emitted only when configured; default behavior unchanged; integration tests + docs + CI green |
| 2 | `EAP-087` | `GEN-48` | OpenClaw `/tools/invoke` bridge | Typed OpenClaw tools-invoke client and runtime bridge tool | Auth + success + policy-denial paths covered; error mapping aligns with EAP contract; docs + CI green |
| 3 | `EAP-088` | `GEN-47` | OpenAI Responses API adapter path | Provider path for `POST /v1/responses` with explicit selection controls | Happy path + disabled/unsupported endpoint behavior tested; no regression to chat-completions path; docs + CI green |

## Dependency Order

1. `EAP-086` unblocks `EAP-087`.
2. `EAP-087` unblocks `EAP-088`.

## Execution Constraint

Only the first non-blocked `Todo` item may be started (`EAP-086`).
