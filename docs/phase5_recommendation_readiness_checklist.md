# Phase 5 Recommendation Readiness Checklist

This checklist tracks the next ordered tranche after Phase 4 to make EAP recommendable without caveats.

## Tranche 1 (ordered)

1. `EAP-064` Resolve open CodeQL high alert in compiler JSON extraction
2. `EAP-065` Add `CODEOWNERS` coverage for critical runtime/docs/workflow paths
3. `EAP-066` Add README quickstart smoke workflow in CI
4. `EAP-067` Publish one-page proof sheet (`why EAP`) with benchmark + failure-mode evidence

## Current status

- [x] `EAP-064` Regex-based JSON extraction replaced with parser-based extraction; noisy-payload regression tests added.
- [x] `EAP-065` `CODEOWNERS` for `agent/`, `environment/`, `protocol/`, `docs/`, and `.github/workflows/`.
- [x] `EAP-066` CI job executes README quickstart path (install + minimal run) on pull requests.
- [x] `EAP-067` Proof sheet published at `docs/eap_proof_sheet.md` and linked from roadmap/docs index.
