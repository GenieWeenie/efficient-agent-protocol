# Phase 7 Competitive Roadmap (OpenClaw + Market Positioning)

Status: In progress (through EAP-079, 2026-02-23)

Current status:
- [x] `EAP-071` interop spike + compatibility matrix published (`docs/openclaw_interop.md`)
- [x] `EAP-072` minimal EAP runtime HTTP endpoints + auth hooks + integration tests
- [x] `EAP-073` OpenClaw plugin adapter MVP (`integrations/openclaw/eap-runtime-plugin`)
- [x] `EAP-074` OpenClaw skill pack (`integrations/openclaw/eap-runtime-plugin/skills`)
- [x] `EAP-075` interop CI lane (`.github/workflows/openclaw-interop.yml`)
- [x] `EAP-076` human approval checkpoints (HITL pause/approve/reject + trace transitions)
- [x] `EAP-077` crash-safe resume and replay (checkpoint persistence + run resume API)
- [x] `EAP-078` MCP interoperability (stdio MCP bridge tool + runtime integration test)
- [x] `EAP-079` evaluation harness + scorecard (CI artifact + regression gate)
- [ ] `EAP-080` onward

## Objective

Make EAP easier to adopt and harder to replace by:

1. Integrating cleanly with OpenClaw workflows.
2. Closing high-impact capability gaps seen in top orchestration stacks.
3. Doubling down on EAP's differentiator: deterministic, observable, pointer-backed execution.

## Research Snapshot (2026-02-23)

- LangGraph positions around durable execution, agent workflows, and production controls.
- AutoGen positions around multi-agent orchestration and framework-level flexibility.
- CrewAI positions around teams/flows for production workflows.
- PydanticAI emphasizes typed outputs and provider abstraction.
- OpenClaw exposes a plugin/skills model and secured API surface (`/v1/*`) with auth controls.

External reference points (snapshot links):
- LangGraph: https://github.com/langchain-ai/langgraph
- AutoGen: https://github.com/microsoft/autogen
- CrewAI: https://github.com/crewAIInc/crewAI
- PydanticAI: https://github.com/pydantic/pydantic-ai
- OpenClaw repo: https://github.com/openclaw/openclaw
- OpenClaw skills docs: https://docs.openclaw.ai/skills
- OpenClaw plugin docs: https://docs.openclaw.ai/tools/plugin
- OpenClaw security docs: https://docs.openclaw.ai/security

Implication:
- EAP should not try to out-market full platform suites immediately.
- EAP should become the "reliability engine" that can run standalone or plug into OpenClaw.

## OpenClaw Fit Assessment

Strong fit, with two practical integration surfaces:

1. Plugin path (recommended first):
   - Build an OpenClaw plugin that exposes EAP workflow operations as OpenClaw tools.
2. Skill path:
   - Ship OpenClaw skills that run curated EAP commands/workflows for common tasks.

Optional validation track:
- Verify whether OpenClaw's `/v1/*` surface can be consumed directly by EAP provider adapters without compatibility shims.

## Ordered Checklist

## Tranche 1: OpenClaw Interop Foundation

1. `EAP-071` OpenClaw interoperability spike and compatibility matrix
   - Deliverable: `docs/openclaw_interop.md`
   - Include: supported versions, auth model, plugin vs skill tradeoffs, known limits
   - Done when: matrix is reproducible and reviewed

2. `EAP-072` EAP HTTP runtime endpoints for external orchestrators
   - Deliverable: minimal API endpoints to run workflow, inspect run status, fetch pointer payload metadata
   - Include: request/response schemas and auth hooks
   - Done when: integration tests pass for happy path + auth failure + invalid payload

3. `EAP-073` OpenClaw plugin adapter (MVP)
   - Deliverable: plugin exposing at least:
     - `run_eap_workflow`
     - `get_eap_run_status`
     - `get_eap_pointer_summary`
   - Done when: OpenClaw can invoke all three operations end-to-end in local env

4. `EAP-074` OpenClaw skill pack for common EAP operations
   - Deliverable: skills for "run", "inspect", "retry failed step", and "export trace"
   - Done when: skills are installable and documented with a 5-minute quickstart

5. `EAP-075` Interop CI lane
   - Deliverable: CI workflow that runs smoke interop tests against pinned OpenClaw versions
   - Done when: branch protection includes this job

## Tranche 2: Competitive Capability Upgrades

6. `EAP-076` Human approval checkpoints (HITL)
   - Add optional step-level pause/approve/reject semantics
   - Done when: execution trace captures approval transitions and rejection reasons

7. `EAP-077` Crash-safe resume and replay
   - Add resumable macro runs from persisted checkpoints
   - Done when: forced process termination can recover and continue without corrupting state

8. `EAP-078` MCP interoperability
   - Add MCP server export for selected EAP tools or a client bridge for MCP tools
   - Done when: at least one reference MCP tool can be executed via EAP runtime
   - Status: complete (added `invoke_mcp_tool` bridge + `tests/integration/test_mcp_interop.py`)

9. `EAP-079` Evaluation harness and scorecard
   - Deliverable: repeatable eval suite (reliability + correctness + latency)
   - Done when: CI publishes trend artifacts and fails on regression thresholds
   - Status: complete (`scripts/eval_scorecard.py`, `docs/eval_thresholds.json`, CI `eval-scorecard` job)

## Tranche 3: Differentiation and Adoption

10. `EAP-080` Vertical starter packs
    - Deliverable: opinionated templates (research assistant, doc ops, local ETL)
    - Done when: each template has green smoke tests and runnable walkthrough docs

11. `EAP-081` Operator telemetry pack
    - Deliverable: first-party dashboards/charts for retries, saturation, fail reasons, and step latency percentiles
    - Done when: maintainer can diagnose a failed run from telemetry alone

12. `EAP-082` "Why EAP now" competitive page refresh
    - Deliverable: refresh `docs/eap_proof_sheet.md` with new interop and eval evidence
    - Done when: proof sheet includes side-by-side capability table + reproducible commands

## Guardrails

- Do not chase every platform feature from larger ecosystems.
- Prioritize reliability, debuggability, and local-first portability.
- Treat OpenClaw integration as a force multiplier, not a rewrite target.

## Success Criteria

- OpenClaw plugin + skill pack both work in local reference setup.
- New interop lane is required in CI.
- EAP can recover interrupted runs deterministically.
- External users can onboard via a starter pack in under 10 minutes.
