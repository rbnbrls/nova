# Technology Stack

**Analysis Date:** 2026-07-11

## Languages

**Primary:**
- Python 3.12 - `services/nova-core/` (FastAPI agent service), `services/ops-bridge/` (webhook bridge)

**Secondary:**
- Bash - `ops/*.sh` closed-loop CI/CD and incident-management scripts
- SQL - `infra/postgres/init/01_schema.sql` schema bootstrap
- YAML - `infra/vector/vector.yaml` (Vector observability pipeline config), `docker-compose.yml`

## Runtime

**Environment:**
- Python 3.12-slim (Docker base image, see `services/nova-core/Dockerfile`)
- Deployed as Docker containers orchestrated by Coolify on a single "Nova AI" VM (see `docker-compose.yml` header comment)

**Package Manager:**
- pip, with pinned versions in `requirements.txt` per service
- Lockfile: none (plain `requirements.txt` with `==` pins, not a lockfile format like `poetry.lock`/`uv.lock`)

## Frameworks

**Core:**
- FastAPI 0.115.6 - `services/nova-core/app/main.py`, `services/ops-bridge/app.py` (HTTP API framework for both Python services)
- Uvicorn 0.34.0 (`[standard]` extras) - ASGI server, entrypoint via `CMD ["uvicorn", "app.main:app", ...]` in each Dockerfile
- Pydantic 2.10.4 / pydantic-settings 2.7.1 - request/response schemas (`services/nova-core/app/models.py`) and env-based settings (`services/nova-core/app/config.py`)

**Testing:**
- Not detected - no test framework, test files, or test config found in either service

**Build/Dev:**
- Docker (multi-service, one Dockerfile per service: `services/nova-core/Dockerfile`, `services/ops-bridge/Dockerfile`)
- Docker Compose - `docker-compose.yml` orchestrates all services for local dev and (via Coolify) production

## Key Dependencies

**Critical:**
- httpx 0.28.1 - async HTTP client used for calling Ollama (`services/nova-core/app/llm.py`), Forgejo API (`services/ops-bridge/app.py`)
- pgvector (`pgvector/pgvector:pg16` image) - Postgres extension for vector similarity search, used for the `memories` table embeddings (`infra/postgres/init/01_schema.sql`)

**Infrastructure:**
- Ollama (`ollama/ollama:latest`, GPU-accelerated) - self-hosted LLM inference server; model `qwen3:14b` for chat, `nomic-embed-text` for embeddings (`services/nova-core/app/config.py`)
- Wyoming protocol services - `rhasspy/wyoming-whisper` (STT, GPU) and `rhasspy/wyoming-piper` (TTS) for voice I/O, integrated with Home Assistant's Assist pipeline (`docker-compose.yml`)
- Vector (`timberio/vector:latest-alpine`) - log/metrics shipping agent, ships Docker logs + host metrics to OpenObserve (`infra/vector/vector.yaml`)
- Caddy 2 - reverse proxy / TLS termination (`Caddyfile`), routes `/dashboard/*` and default traffic to `nova-core:8080`

## Configuration

**Environment:**
- Root `.env` file (referenced via `env_file: .env` in `docker-compose.yml` for `nova-core`, `vector`, `ops-bridge`); `.env.example` documents required vars (not read for security — see forbidden files policy)
- `services/nova-core/app/config.py` uses `pydantic-settings.BaseSettings` with `env_file=".env"` and sensible defaults (e.g. `nova_env`, `ollama_base_url`, `postgres_*`, `nova_whatsapp_users`)
- `services/ops-bridge/app.py` reads config directly via `os.environ.get(...)` (no pydantic-settings): `FORGEJO_URL`, `FORGEJO_REPO`, `FORGEJO_TOKEN`, `BRIDGE_TOKEN`, `BRIDGE_ALERT_LABELS`
- `ops/config.env` (gitignored, copied from `ops/config.env.example`) configures the bash ops loop (Coolify API token, Forgejo, Claude CLI args) - see `ops/lib.sh`
- `ops/secrets/infra.env.example` - template for infra-provisioning secrets (Proxmox audit script)

**Build:**
- `services/nova-core/Dockerfile`, `services/ops-bridge/Dockerfile` - both `python:3.12-slim`, non-buffered/no-bytecode env, `pip install -r requirements.txt`, exposed on container port 8080
- `docker-compose.yml` - defines all 8 services (nova-core, postgres, ollama, whisper, piper, vector, ops-bridge, caddy)
- `Caddyfile` - reverse proxy config; only the WhatsApp webhook path is intended for public exposure (via Cloudflare Tunnel, commented placeholder)

## Platform Requirements

**Development:**
- Docker + Docker Compose (`docker compose up -d` per `docker-compose.yml` header comment)
- NVIDIA Container Toolkit for local GPU passthrough if running `ollama`/`whisper` with GPU acceleration

**Production:**
- Single "Nova AI" VM with NVIDIA GPU, provisioned on Proxmox (see `ops/provision/audit-proxmox.sh`)
- Coolify as the deployment/orchestration platform (Phase 1), driving `docker-compose.yml`-equivalent service definitions
- Cloudflare Tunnel for exposing only the WhatsApp webhook publicly (planned, Phase 4 — commented out in `Caddyfile`)

---

*Stack analysis: 2026-07-11*
