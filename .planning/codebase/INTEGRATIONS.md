# External Integrations

**Analysis Date:** 2026-07-11

## APIs & External Services

**LLM Inference:**
- Ollama (self-hosted, not third-party SaaS) - chat + tool-calling via `/api/chat`, embeddings via `nomic-embed-text`
  - Client: raw `httpx.AsyncClient` calls in `services/nova-core/app/llm.py`
  - Config: `OLLAMA_BASE_URL` (default `http://ollama:11434`), `NOVA_MODEL` (default `qwen3:14b`), `NOVA_EMBED_MODEL` (default `nomic-embed-text`) — `services/nova-core/app/config.py`
  - Auth: none (internal Docker network service)

**Issue Tracking / Git Hosting:**
- Forgejo (self-hosted, `git.7rb.nl/ruben/nova`) - used as the single source of truth for the incident queue and as the CI/CD control surface
  - Client: raw `httpx` calls in `services/ops-bridge/app.py` (create/comment issues, label lookup) and `curl` in `ops/issue.sh`, `ops/observe.sh`, `ops/heal.sh`
  - Auth: `FORGEJO_TOKEN` (bearer token, env var), repo `FORGEJO_REPO` (default `ruben/nova`)

**Deployment Platform:**
- Coolify (self-hosted PaaS on the Nova VM) - deployment automation, redeploys on merge to main
  - Client: `coolify_api()` helper in `ops/lib.sh` (curl with `Authorization: Bearer $COOLIFY_API_TOKEN`)
  - Auth: `COOLIFY_API_TOKEN`, `COOLIFY_URL` (from `ops/config.env`)

**AI Coding Agent (ops loop):**
- Claude CLI (`claude -p`, headless) - autonomous incident remediation ("heal") in `ops/heal.sh`
  - Invocation: `claude "${CLAUDE_ARGS[@]}"` with `--max-turns` (default 40) and optional `--model` (`CLAUDE_MODEL` env var)

**Planned / Stubbed (not yet implemented — Phase 5):**
- Microsoft Graph API - shared Outlook mailbox email listing, stub in `services/nova-core/app/tools/email.py` (`list_recent_emails`); real integration deferred, scope planned: `Mail.Read`
- CalDAV (self-hosted: Home Assistant local calendar, Radicale, or Nextcloud) - calendar tool stub in `services/nova-core/app/tools/calendar.py` (`list_events`, `create_event`)

## Data Storage

**Databases:**
- PostgreSQL 16 with pgvector extension (`pgvector/pgvector:pg16` Docker image)
  - Connection: built from `POSTGRES_HOST`/`PORT`/`DB`/`USER`/`PASSWORD` env vars via `settings.database_url` property in `services/nova-core/app/config.py`
  - Client: not yet wired up in application code (tools in `services/nova-core/app/tools/*.py` are stubs; no ORM/driver import found yet)
  - Schema: `infra/postgres/init/01_schema.sql` — tables: `users`, `tasks`, `memories` (768-dim vector column, HNSW cosine index), `messages`
  - Extensions: `vector` (pgvector), `uuid-ossp`

**File Storage:**
- Local filesystem only, via Docker volumes (`./data/postgres`, `./data/ollama`, `./data/whisper`, `./data/piper`, `./data/caddy` in `docker-compose.yml`)

**Caching:**
- None detected

## Authentication & Identity

**Auth Provider:**
- Custom / none - no user-facing auth provider integrated yet
- Household identity resolution: `services/nova-core/app/identity.py` maps a WhatsApp E.164 sender number to a household user (`Ruben`, `Meral`, or fallback `household`) via `NOVA_WHATSAPP_USERS` env var (format `"number:name,number:name"`)
- `ops-bridge` webhook auth: shared-secret header `X-Bridge-Token` checked against `BRIDGE_TOKEN` env var (`services/ops-bridge/app.py`)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/error-tracking SaaS detected)

**Logs:**
- Vector (`timberio/vector:latest-alpine`) ships Docker container logs (via `/var/run/docker.sock`) and host metrics to OpenObserve
  - Config: `infra/vector/vector.yaml`
  - OpenObserve endpoint/auth: `OPENOBSERVE_URL`, `OPENOBSERVE_ORG`, `OPENOBSERVE_USER`, `OPENOBSERVE_PASSWORD` (basic auth), gzip-compressed JSON for logs, Prometheus remote-write for metrics
  - OpenObserve runs as a separate Coolify service (not in this repo's `docker-compose.yml`)

**Alerting → Incident Bridge:**
- OpenObserve alert destinations POST to `ops-bridge` (`POST /webhooks/openobserve`), which fingerprints (`sha1(alert_name|stream)`) and creates or comments on a Forgejo issue for dedup — `services/ops-bridge/app.py`
- Self-healing loop: `ops/triage.sh` (systemd timer) picks up `auto-heal`-labeled issues → `ops/heal.sh` runs headless Claude CLI to produce a fix branch → merge → Coolify redeploy → `ops/observe.sh` verifies deployment health

## CI/CD & Deployment

**Hosting:**
- Single self-hosted "Nova AI" VM (Proxmox-provisioned, see `ops/provision/audit-proxmox.sh` — read-only host audit script)

**CI Pipeline:**
- Custom closed-loop bash pipeline (not GitHub Actions/GitLab CI): `ops/pipeline.sh`, `ops/deploy.sh`, `ops/observe.sh`, `ops/heal.sh`, `ops/triage.sh`, `ops/issue.sh` — see `ops/README.md` for the full diagram (Vector → OpenObserve → ops-bridge → Forgejo issues → triage.sh → heal.sh (Claude CLI) → merge → Coolify redeploy → observe.sh verification)

## Environment Configuration

**Required env vars (non-exhaustive, by service):**
- `nova-core`: `NOVA_ENV`, `NOVA_LOG_LEVEL`, `NOVA_TIMEZONE`, `OLLAMA_BASE_URL`, `NOVA_MODEL`, `NOVA_EMBED_MODEL`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `NOVA_WHATSAPP_USERS`
- `ops-bridge`: `FORGEJO_URL`, `FORGEJO_REPO`, `FORGEJO_TOKEN`, `BRIDGE_TOKEN`, `BRIDGE_ALERT_LABELS`
- `vector`: `OPENOBSERVE_URL`, `OPENOBSERVE_ORG`, `OPENOBSERVE_USER`, `OPENOBSERVE_PASSWORD`
- `postgres` (compose-level): `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- ops bash loop (`ops/config.env`, gitignored): `COOLIFY_API_TOKEN`, `COOLIFY_URL`, `FORGEJO_TOKEN`, `CLAUDE_MAX_TURNS`, `CLAUDE_MODEL`

**Secrets location:**
- Root `.env` (gitignored, templated by `.env.example`) for the Docker Compose stack
- `ops/config.env` (gitignored, templated by `ops/config.env.example`) for the bash ops/CI loop
- `ops/secrets/infra.env.example` template for infra-provisioning secrets (`ops/secrets/` gitignored except `.gitkeep`)

## Webhooks & Callbacks

**Incoming:**
- `POST /webhooks/openobserve` on `ops-bridge` (`services/ops-bridge/app.py`) - receives OpenObserve alert payloads, protected by `X-Bridge-Token` header
- WhatsApp webhook (planned, Phase 4) - not yet implemented; `Caddyfile` reserves a commented-out public route (`/webhooks/whatsapp*` via Cloudflare Tunnel) pointing at `nova-core`

**Outgoing:**
- `ops-bridge` → Forgejo API (`POST /issues`, `POST /issues/{n}/comments`, `GET /labels`) to create/dedup incident issues
- Vector → OpenObserve (`POST /api/{org}/docker/_json` for logs, `POST /api/{org}/prometheus/api/v1/write` for metrics)

---

*Integration audit: 2026-07-11*
