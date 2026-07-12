<!-- generated-by: gsd-doc-writer -->

# Nova — Local AI Household Assistant

Private, self-hosted household assistant for Ruben & Méral. Nova runs on a Proxmox server
(PNY RTX 2000 Blackwell, ~16 GB VRAM), reachable by **text (WhatsApp)** and **voice
(ESPHome satellites + iPhone)**, and maintains a shared household plan covering **tasks,
calendar, and important emails** from a shared Outlook mailbox.

> **Privacy boundary:** the reasoning model and all household data stay local — no prompts
> or content go to a cloud LLM. Only two channels reach the internet by nature: WhatsApp
> (Meta Cloud API) and the Outlook mailbox (Microsoft Graph).

## Architecture

```
WhatsApp ─┐
Voice ────┤→ Nova Core (agent loop + tools + memory) ─→ Ollama (local LLM, GPU)
Telegram ─┘        │            │             │
              Tasks(PG)   Calendar(CalDAV)  Email(MS Graph)
```

Nova Core (FastAPI) is a single channel-agnostic brain exposing an OpenAI-compatible
`/v1/chat/completions` endpoint. Every channel funnels text into the same agent loop,
so tools and memory are written once. Home Assistant is reused as the voice I/O layer
and points its conversation agent at Nova Core.

## Installation

```bash
git clone https://git.7rb.nl/ruben/nova.git
cd nova
cp .env.example .env          # then edit values
docker compose up -d
```

The stack includes:
- **nova-core** — FastAPI agent loop (Python 3.12)
- **postgres** — pgvector/pg16 for tasks, memory, and audit logging
- **ollama** — local LLM serving (RTX 2000 Blackwell via GPU passthrough)
- **whisper** / **piper** — voice STT/TTS (Wyoming protocol, Phase 6)
- **radicale** — self-hosted CalDAV calendar
- **caddy** — reverse proxy (LAN dashboard, API, WhatsApp webhook)
- **vector** — log/metric shipping to OpenObserve
- **ops-bridge** — OpenObserve alert webhook → Forgejo issue (dedup)

## Quick start

1. Copy the environment file and configure required secrets:
   ```bash
   cp .env.example .env
   ```

2. Start the stack:
   ```bash
   docker compose up -d
   ```

3. Pull the model into the Ollama container (first run only):
   ```bash
   docker compose exec ollama ollama pull qwen3:14b
   ```

4. Smoke-test the API:
   ```bash
   curl -s localhost:8080/health
   curl -s localhost:8080/v1/chat/completions \
     -H 'content-type: application/json' \
     -d '{"user":"Ruben","messages":[{"role":"user","content":"add milk to the shopping list"}]}'
   ```

## Usage examples

**Chat with Nova (OpenAI-compatible API):**
```bash
curl -s localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"user":"Ruben","messages":[{"role":"user","content":"What do I have planned today?"}]}'
```

**View the LAN dashboard:**
```
http://localhost:8080/dashboard
```
The dashboard provides a live view of tasks, calendar events, and the recent audit log
(SSE-streamed, auto-refreshing every 15 seconds).

**WhatsApp webhook (Phase 4):**
```
POST /webhooks/whatsapp    # Meta Cloud API webhook endpoint
GET  /webhooks/whatsapp    # webhook verification handshake
```

## Build phases

| Phase | What | Status |
|------:|------|--------|
| 0 | Proxmox infra: GPU passthrough, Docker, NVIDIA toolkit | host setup |
| 1 | Coolify self-hosted CI/CD (git push-to-deploy) | host setup |
| 2 | Local runtime: Ollama + Postgres/pgvector | scaffolded |
| 3 | **Nova Core**: agent loop, identity, memory, OpenAI API | **scaffolded** |
| 4 | WhatsApp (Meta Cloud API) + Telegram bot | live |
| 5 | Household tools: tasks, CalDAV, Outlook/Graph email | stubs in place |
| 6 | Voice: HA Assist + Whisper/Piper, ESPHome, iPhone | compose wired |
| 7 | Proactive: briefings, reminders, better TTS | pending |
| 8 | Static LAN dashboard (calendar + tasks) | live |

See the full roadmap with extension tracks at [docs/roadmap.md](./docs/roadmap.md).

## Repository layout

```
docker-compose.yml         Full stack (nova-core, postgres, ollama, whisper, piper, caddy)
Caddyfile                  Reverse proxy (LAN dashboard/API + WhatsApp webhook)
.env.example               Config template — secrets live in Coolify, never in git
infra/postgres/init/       DB schema (tasks + memory), runs on first Postgres boot
ops/                       Closed-loop incident management: Forgejo issues → triage → heal
services/ops-bridge/       OpenObserve alert webhook → Forgejo issue (dedup)
infra/vector/              Log/metric shipping into OpenObserve
services/nova-core/        The FastAPI brain
  app/
    main.py                FastAPI: /health, /v1/chat/completions, /dashboard/*
    agent.py               LLM ↔ tools agent loop
    llm.py                 Ollama chat client
    identity.py            Channel identity → household user
    config.py              Env-based settings
    tools/                 Household capabilities (tasks, calendar, email)
```

## Deployment

Deploys are git-driven via **Coolify** on the Nova AI VM (Phase 1). Push to `main` →
Coolify rebuilds and redeploys each service. Secrets are managed in Coolify, not in git.

**Closed feedback loop:** [ops/](./ops/) implements closed-loop incident management with
**Forgejo issues** as the single incident queue — fed by OpenObserve alerts (logs/metrics
via Vector → `ops-bridge` webhook), deploy verification, and user-filed issues. Triage
and auto-heal scripts can diagnose and commit fixes, reporting back as issue comments.
See [ops/README.md](./ops/README.md).

<!-- VERIFY: git remote URL -->
<!-- VERIFY: Coolify dashboard URL -->
<!-- VERIFY: Forgejo issues URL -->
