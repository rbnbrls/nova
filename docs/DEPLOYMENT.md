<!-- generated-by: gsd-doc-writer -->

# Deployment

Nova is a self-hosted household AI assistant deployed as a Docker Compose stack on a Proxmox
VM (GPU-accelerated — the host has an NVIDIA RTX PRO 2000 Blackwell passed through to the
nova-ai VM). Deployments are git-driven
via **Coolify** — push to `main` and Coolify rebuilds and redeploys each service. Secrets live
in Coolify, never in git.

## Deployment targets

| Target | Config file | Purpose |
|--------|------------|---------|
| **Production stack** | `docker-compose.yml` | Full Nova stack (nova-core, postgres, ollama, whisper, piper, vector, ops-bridge, radicale, caddy) |
| **Staging stack** | `docker-compose.staging.yml` | Isolated staging instance on port 8081, separate DB, for model evaluation before promotion |
| **Coolify** | via `ops/deploy.sh` | Self-hosted CI/CD platform orchestrating deployments on the Nova AI VM | <!-- VERIFY: Coolify dashboard URL -->
| **Caddy** | `Caddyfile` | Reverse proxy routing LAN dashboard, API, and WhatsApp webhook |

Deployment is fully containerized — the Dockerfiles are at `services/nova-core/Dockerfile` and
`services/ops-bridge/Dockerfile`, both multi-stage builds (base → tester → final) on Python 3.12.

`ollama` and `whisper` use GPU passthrough via `deploy.resources.reservations.devices` (driver
`nvidia`) — this requires the **NVIDIA Container Toolkit** installed and the `nvidia` Docker
runtime configured on the deployment host (nova-ai VM). The host's RTX PRO 2000 is passed
through to the VM (Proxmox `hostpci0: mapping=rtx-pro-2000,pcie=1`); without a working NVIDIA
driver/container runtime inside the VM, the GPU blocks prevent both containers from starting
(stuck in "Created", Pid=0) and cascade to nova-core → caddy.

> **Known deployment pitfall (2026-08-03):** the Coolify server setting `delete_unused_networks`
> (plus the daily cleanup job `0 0 * * *`) can prune the `coolify` Docker network while no app is
> running, breaking the next deploy with `Error response from daemon: network coolify not found`.
> Keep that setting disabled, or recreate the network with
> `docker network create coolify --attachable` on the deployment server.

## Build pipeline

Nova uses a **closed-loop deployment pipeline** orchestrated by scripts in `ops/`:

### 1. Coolify webhook (trigger)

Push to `main` → Coolify detects the change and rebuilds each configured service from its
Dockerfile. Services are defined by their Coolify resource UUIDs configured in `ops/config.env.example`
as `NOVA_SERVICES` (comma-separated `name:uuid` pairs).

### 2. Manual / programmatic deploy

`ops/deploy.sh` triggers Coolify deployments via its API and polls until completion:

```bash
# Deploy staging only (default)
ops/deploy.sh

# Deploy production only
ops/deploy.sh --prod

# Deploy both (staging first, then production after 15s)
ops/deploy.sh --all

# Deploy specific service(s)
ops/deploy.sh nova-core caddy
```

Configurable timeouts: `DEPLOY_TIMEOUT_SECONDS=600` (max wait per service) in `ops/config.env.example`.

### 3. Staging → production promotion

`ops/promote.sh` gates the staging-to-production transition through three phases:

1. **Health check** — polls staging's `/health` endpoint 5 times (`STAGING_HEALTH_URL`)
2. **Test suite** — runs `ops/run-tests.sh` (pytest, ruff, mypy)
3. **Production deploy** — calls `ops/deploy.sh --prod`

```bash
ops/promote.sh           # full gate
ops/promote.sh --force   # skip health check
```

Exit codes: 0 = success, 1 = health fail, 2 = test fail, 3 = deploy fail.

### 4. Closed-loop pipeline

`ops/pipeline.sh` runs the full **deploy → observe → triage/heal → redeploy** loop:

```
deploy.sh
  │
  ▼
observe.sh  ──healthy──► exit 0
  │ unhealthy
  ▼
file Forgejo issue (incident,monitoring,auto-heal)
  │
  ▼
triage.sh picks up auto-heal issues
  │
  ▼
heal.sh — Claude Code diagnoses, fixes, commits, tests
  │
  ▼
push fix → Coolify redeploys → loop repeats
```

The loop caps retries at `HEAL_MAX_ATTEMPTS=2` per run. See `ops/config.env.example` for all knobs.

### 5. Test suite

`ops/run-tests.sh` runs on a dedicated `.venv-tests` virtualenv:

```bash
ops/run-tests.sh
```

Executes: pytest for both services, ruff lint, and mypy type checking. Must pass before
`promote.sh` allows production deployment.

## Environment setup

All environment variables for production are documented in `docs/CONFIGURATION.md`. Key deployment
differences from local development:

- **Secrets** (tokens, passwords) must be set in **Coolify's environment variable manager**,
  not in a local `.env` file. Coolify injects them at container runtime.
- The `.env.example` file serves as a template only — copy it to `.env` for reference, but
  never commit real secrets.

**Required for deployment:**

| Variable | Where set | Purpose |
|----------|-----------|---------|
| `COOLIFY_API_TOKEN` | `ops/config.env.example` | Authenticate deploy/promote scripts against Coolify API |
| `COOLIFY_URL` | `ops/config.env.example` | Coolify API base URL |
| `NOVA_SERVICES` | `ops/config.env.example` | `name:uuid` pairs of Coolify resources to deploy |
| `FORGEJO_TOKEN` | `.env` + `ops/config.env.example` | Issue read/write for incident tracking (ops-bridge + ops scripts) |
| `OPENOBSERVE_URL` / `OPENOBSERVE_ORG` / `OPENOBSERVE_USER` / `OPENOBSERVE_PASSWORD` | `.env` | Vector log/metric shipping | <!-- VERIFY: OpenObserve URL -->
| `BRIDGE_TOKEN` | `.env` | Shared secret for OpenObserve → ops-bridge authentication |
| `POSTGRES_PASSWORD` | `.env` (Coolify) | Database credentials |
| `WHATSAPP_VERIFY_TOKEN` / `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_APP_SECRET` | `.env` (Coolify) | Meta Cloud API for WhatsApp channel | <!-- VERIFY: WhatsApp credentials -->

The staging stack (`docker-compose.staging.yml`) uses a separate env file (`.env.staging.example`)
with a distinct database (`POSTGRES_DB=nova_staging`) on the same Postgres instance. Staging
traffic is isolated to port 8081, and can be configured to test different models by overriding
`NOVA_MODEL` in `.env.staging.example`.

## Rollback procedure

Nova does not have an automated rollback script. The recommended rollback approaches are:

1. **Coolify dashboard** — redeploy any previous build from the Coolify UI
   (Coolify retains build history per service).
   <!-- VERIFY: Coolify dashboard URL -->

2. **Downgrade image tag** — if using specific Docker image tags, revert the tag in
   Coolify's service configuration and redeploy.

3. **Git revert** — revert the problematic commit on `main`, push, and Coolify redeploys
   automatically:

   ```bash
   git revert <bad-commit>
   git push origin main
   ```

4. **Heal branch** — if the deployment failure triggered the closed-loop pipeline,
   the fix is committed on a branch and can be merged to deploy immediately:

   ```bash
   git merge nova/heal-<timestamp>
   git push origin main
   ```

For model regression specifically (staging model degraded metrics vs. production), manually
revert `NOVA_MODEL` in `.env` to the previous model and redeploy.

## Monitoring

Nova's observability stack is built on **Vector + OpenObserve** with **closed-loop incident
management via Forgejo issues**.

### Log and metric shipping

[Vector](https://vector.dev) (timberio/vector:latest-alpine) collects:

- **Docker container logs** — from all Compose services via `docker_logs` source
- **Host metrics** — CPU, memory, disk, network every 30 seconds via `host_metrics` source

Both streams ship to **OpenObserve** (self-hosted as a Coolify service) defined in
`infra/vector/vector.yaml`. Configuration uses env-based credentials (`OPENOBSERVE_URL`,
`OPENOBSERVE_ORG`, `OPENOBSERVE_USER`, `OPENOBSERVE_PASSWORD`).

### Health checks

- **nova-core**: `GET /health` returns `{"status": "ok", "ollama_ready": true/false}` on port 8080
- **ops-bridge**: `GET /health` returns status on port 8085
- Docker Compose healthchecks are configured for nova-core, postgres, and ops-bridge
- `ops/observe.sh` polls configurable health endpoints post-deploy (retries × interval)

### Alerting and incident management

OpenObserve alerts → `ops-bridge` (FastAPI webhook receiver, port 8085) → **Forgejo issue**:

1. OpenObserve fires an alert webhook (authenticated with `X-Bridge-Token` header)
2. `ops-bridge` fingerprints the alert, deduplicates against open issues, and creates or
   comments on a Forgejo issue with labels `incident,monitoring,auto-heal`
3. `ops/triage.sh` (run by systemd timer every 5 minutes) picks up open `auto-heal` issues
4. `ops/heal.sh` invokes Claude Code headless to diagnose and fix, reporting back as issue
   comments

Full details in `ops/README.md`.

### Post-deploy verification

`ops/observe.sh` captures on failure:

- Health endpoint responses and HTTP status codes
- Full container state (`docker ps -a`)
- Recent container logs (`docker logs --tail 200`)
- Last 10 commits on the deployed branch

All of this is filed as the body of a Forgejo incident issue — the single source of truth
for deployment health.

<!-- VERIFY: OpenObserve dashboard URL -->
<!-- VERIFY: Forgejo issues URL (git.7rb.nl/ruben/nova/issues) -->
<!-- VERIFY: Coolify API URL -->
