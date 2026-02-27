# Documentation Index

## Getting Started

| Doc | Description |
| --- | --- |
| [configuration.md](configuration.md) | Environment variables, validation rules, provider setup |
| [architecture.md](architecture.md) | System architecture, component map, data flows |
| [custom_tool_authoring.md](custom_tool_authoring.md) | Guide to building and registering custom tools |
| [pointer_internals.md](pointer_internals.md) | Pointer-backed state lifecycle, storage, resolution |
| [troubleshooting.md](troubleshooting.md) | Common issues and fixes |
| [eap_proof_sheet.md](eap_proof_sheet.md) | Reproducible evidence and command-level validation |

## Workflow and Execution

| Doc | Description |
| --- | --- |
| [workflow_schema.md](workflow_schema.md) | Workflow graph schema and validation |
| [tools.md](tools.md) | Built-in tools reference |
| [plugin_spec.md](plugin_spec.md) | Third-party plugin contract and discovery |
| [distributed_execution.md](distributed_execution.md) | Coordinator-worker protocol for multi-node execution |

## Storage and State

| Doc | Description |
| --- | --- |
| [storage_backends.md](storage_backends.md) | Pluggable backends (SQLite, Redis, PostgreSQL) |
| [storage_lifecycle.md](storage_lifecycle.md) | Pointer TTL, expiry, and cleanup |
| [migrations.md](migrations.md) | SQLite schema migration policy |
| [state_backup_restore.md](state_backup_restore.md) | Backup/restore workflows and recovery drills |

## Operations and Deployment

| Doc | Description |
| --- | --- |
| [self_hosted_control_plane.md](self_hosted_control_plane.md) | Docker Compose reference stack for self-hosting |
| [remote_ops_governance.md](remote_ops_governance.md) | Multi-user auth, scopes, and run ownership |
| [observability.md](observability.md) | Structured logging and metrics export |
| [operator_telemetry_pack.md](operator_telemetry_pack.md) | Diagnostic export and telemetry pack guide |
| [soak_chaos_reliability.md](soak_chaos_reliability.md) | Soak tests and chaos/fault-injection harness |
| [maintainer_runbook.md](maintainer_runbook.md) | Daily operations, triage, and incident response |

## Quality and Evaluation

| Doc | Description |
| --- | --- |
| [evaluation_harness.md](evaluation_harness.md) | CI-gated evaluation suite |
| [benchmarks.md](benchmarks.md) | Performance baselines and regression gates |

## Interop

| Doc | Description |
| --- | --- |
| [openclaw_interop.md](openclaw_interop.md) | OpenClaw compatibility analysis and integration paths |
| [sdk_contract.md](sdk_contract.md) | TypeScript/Go SDK contract |

## Starter Packs

| Doc | Description |
| --- | --- |
| [starter_packs/README.md](starter_packs/README.md) | Overview of starter pack templates |
| [starter_packs/research_assistant.md](starter_packs/research_assistant.md) | Research assistant walkthrough |
| [starter_packs/doc_ops.md](starter_packs/doc_ops.md) | Doc ops walkthrough |
| [starter_packs/local_etl.md](starter_packs/local_etl.md) | Local ETL walkthrough |

## Contract and Policy

| Doc | Description |
| --- | --- |
| [v1_contract.md](v1_contract.md) | v1 compatibility contract definition |
| [v1_stabilization_checklist.md](v1_stabilization_checklist.md) | v1 readiness checklist |
| [typing_policy.md](typing_policy.md) | Static typing enforcement plan and residual exclusions |
| [execution_protocol.md](execution_protocol.md) | Linear-first execution queue and gates |

## Release

| Doc | Description |
| --- | --- |
| [release.md](release.md) | Release process and versioning |
| [release_notes_template.md](release_notes_template.md) | Template for release notes |
| [releases/v0.1.8.md](releases/v0.1.8.md) | Release notes for v0.1.8 |

## Roadmaps

| Doc | Description |
| --- | --- |
| [phase5_recommendation_readiness_checklist.md](phase5_recommendation_readiness_checklist.md) | Early recommendation readiness checklist |
| [phase7_competitive_openclaw_roadmap.md](phase7_competitive_openclaw_roadmap.md) | OpenClaw interop roadmap (completed) |
| [phase7_tranche4_scope.md](phase7_tranche4_scope.md) | Tranche 4 scope (completed) |
| [phase8_adoption_limits_closure_roadmap.md](phase8_adoption_limits_closure_roadmap.md) | Adoption improvements (completed) |
| [phase9_production_readiness_roadmap.md](phase9_production_readiness_roadmap.md) | Production readiness controls (completed) |
| [phase10_competitiveness_hardening_roadmap.md](phase10_competitiveness_hardening_roadmap.md) | Competitive hardening (completed) |
| [phase11_typing_rigor_completion_roadmap.md](phase11_typing_rigor_completion_roadmap.md) | Typing rigor completion (in progress) |
| [phase12_v1_launch_readiness_roadmap.md](phase12_v1_launch_readiness_roadmap.md) | V1 launch readiness stabilization (planned) |
