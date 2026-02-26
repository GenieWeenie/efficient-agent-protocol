# Security Policy

## Supported Versions

This project is currently pre-1.0. Security fixes are provided for:

- latest `main`
- latest tagged release line

Older tags may not receive backported fixes.

## Reporting a Vulnerability

Please do not open public issues for suspected vulnerabilities.

Preferred disclosure channel:

1. Open a private GitHub Security Advisory for this repository.
2. If private advisory is unavailable, open a regular issue with minimal details and request a private channel.

## Response Expectations

- Initial triage acknowledgement: within 72 hours.
- Status update cadence: at least every 7 days until resolution.
- Fix target: as quickly as possible based on severity and exploitability.

## Disclosure Process

1. Triage and reproduce.
2. Develop and validate a fix.
3. Publish patched release.
4. Publish advisory notes with impacted/fixed versions and mitigation guidance.

## Runtime Expression Evaluation Hardening

Branch-condition evaluation paths are constrained to a safe expression subset and reject unsafe constructs
(for example function calls, attribute access, and non-boolean outputs).

Operator guidance:

1. Treat branch-condition validation failures as a security signal, not a runtime convenience error.
2. Keep branch expressions declarative and data-driven.
3. Restrict workflow authoring rights in multi-tenant deployments.
