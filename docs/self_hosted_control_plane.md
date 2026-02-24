# Self-Hosted Control-Plane Reference (EAP-093)

This reference stack provides a concrete remote-runtime path for teams that need more than local-only operation.

## What You Get

- Runtime API service exposing `/v1/eap/*` endpoints over HTTP.
- Persistent state volume (`eap_state`) for run summaries and pointer storage.
- Lightweight operator UI for run and pointer visibility.

Compose assets:
- `deploy/self_hosted/docker-compose.yml`
- `deploy/self_hosted/.env.example`
- `deploy/self_hosted/Dockerfile`

## Prerequisites

- Docker Engine with Compose v2.
- Open inbound ports only as needed:
  - runtime API: `8080` (default)
  - operator UI: `8501` (default)

## Start The Stack (One Command)

From repository root:

```bash
cp deploy/self_hosted/.env.example deploy/self_hosted/.env
# edit deploy/self_hosted/.env and set a strong EAP_RUNTIME_BEARER_TOKEN
docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml up --build -d
```

Stop:

```bash
docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml down
```

## Validate Remote Runtime (Smoke)

Run the remote smoke check:

```bash
python scripts/self_hosted_stack_smoke.py \
  --base-url http://127.0.0.1:8080 \
  --bearer-token "<your-runtime-token>" \
  --artifact-path artifacts/self_hosted/self_hosted_smoke.json
```

The smoke validates:
- `POST /v1/eap/macro/execute`
- `GET /v1/eap/runs/{run_id}`
- `GET /v1/eap/pointers/{pointer_id}/summary`

## Deployment Topology

- `runtime` container:
  - Runs `scripts/eap_runtime_service.py`.
  - Requires bearer auth for all `/v1/eap/*` endpoints.
  - Registers a minimal tool set (`fetch_user_data`, `analyze_data`) by default.
- `operator-ui` container:
  - Runs `scripts/eap_operator_ui.py`.
  - Read-only dashboard over the shared SQLite state DB.
- Shared named volume: `eap_state` mounted at `/var/lib/eap`.

## Auth Model

- Runtime API expects `Authorization: Bearer <token>`.
- Token source: `EAP_RUNTIME_BEARER_TOKEN` in `deploy/self_hosted/.env`.
- Requests without valid bearer token return `401 unauthorized`.
- Runtime also supports scoped tokens via `--scoped-auth-config` for multi-user governance.
- Scoped auth defaults to `--policy-profile strict` unless overridden.

Scope baseline:
- `runs:execute`, `runs:resume`, `runs:read`, `pointers:read`
- elevated cross-run scopes: `runs:resume:any`, `runs:read:any`, `pointers:read:any`

Ownership baseline:
- run owners can read/resume their own runs.
- cross-run access requires `*:any` scope.
- pointer summary checks ownership when pointer metadata includes `execution_run_id`.

See `docs/remote_ops_governance.md` for governance rules and scoped token examples.
See profile/template matrix and deny-by-default behavior in `docs/remote_ops_governance.md`.

## Credential Management

- Use a strong, randomly generated runtime token.
- Prefer role-scoped tokens for operators instead of sharing one global token.
- Do not commit `deploy/self_hosted/.env` to source control.
- Rotate token by updating `EAP_RUNTIME_BEARER_TOKEN` and restarting the stack:

```bash
docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml up -d --force-recreate
```

Scoped-token rollout pattern:
1. Keep the admin token for break-glass only.
2. Issue dedicated scoped tokens per operator role.
3. Audit and rotate `*:any` scopes first.

## TLS / Proxy Guidance

The reference stack exposes plain HTTP by default. For production:

- Put the runtime API behind a reverse proxy with TLS termination (Nginx, Caddy, Traefik, or cloud LB).
- Restrict direct access to container ports from public networks.
- Forward the `Authorization` header unchanged.
- Restrict operator UI access to internal/VPN users.

Suggested minimums:
- TLS 1.2+ only.
- Rate limits on runtime API endpoints.
- Access logs enabled on the proxy.

## Backup / Restore Basics

State is stored in the `eap_state` volume.

Backup:

```bash
mkdir -p backups
docker run --rm -v eap_state:/src -v "$PWD/backups:/dst" alpine \
  sh -c 'tar czf /dst/eap_state_$(date +%Y%m%d_%H%M%S).tgz -C /src .'
```

Restore (from a backup archive):

```bash
docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml down
docker run --rm -v eap_state:/dst -v "$PWD/backups:/src" alpine \
  sh -c 'rm -rf /dst/* && tar xzf /src/<backup-file>.tgz -C /dst'
docker compose --env-file deploy/self_hosted/.env -f deploy/self_hosted/docker-compose.yml up -d
```

## CI Coverage

CI runs an automated self-hosted smoke lane that:
- boots the compose stack,
- executes `scripts/self_hosted_stack_smoke.py`,
- verifies operator UI reachability,
- uploads smoke artifacts and compose logs.
