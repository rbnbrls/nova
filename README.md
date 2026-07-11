# Nova — Local AI Household Assistant

Private, self-hosted household assistant for Ruben & Méral. Runs on a Proxmox server
(PNY RTX 2000 Blackwell, ~16 GB VRAM). Reachable by **text (WhatsApp)** and **voice
(ESPHome satellites + iPhone)**, and keeps a shared household plan: **tasks, calendar,
and important emails** from a shared Outlook mailbox.

> **Privacy boundary:** the reasoning model and all household data stay local — no prompts
> or content go to a cloud LLM. Only two *channels* reach the internet by nature: WhatsApp
> (Meta Cloud API) and the Outlook mailbox (Microsoft Graph).

## Architecture

`Nova Core` (FastAPI) is a single channel-agnostic brain exposing an **OpenAI-compatible
API**. Every channel funnels text into the same agent loop, so tools and memory are written
once. Home Assistant is reused only as the voice I/O layer and points its conversation agent
at Nova Core.

```
WhatsApp ─┐
Voice ────┤→ Nova Core (agent loop + tools + memory) ─→ Ollama (local LLM, GPU)
iPhone ───┘        │            │             │
              Tasks(PG)   Calendar(CalDAV)  Email(MS Graph)
```

See the full roadmap: [plan](./docs/roadmap.md) *(source: approved plan file)*.

## Repository layout

```
docker-compose.yml         Full stack (nova-core, postgres, ollama, whisper, piper, caddy)
Caddyfile                  Reverse proxy (LAN dashboard/API + WhatsApp webhook)
.env.example               Config template — real secrets live in Coolify, never in git
infra/postgres/init/       DB schema (tasks + memory), runs on first Postgres boot
ops/                       Closed-loop incident mgmt: Forgejo issues → triage → heal
services/ops-bridge/       OpenObserve alert webhook → Forgejo issue (dedup)
infra/vector/              Log/metric shipping into OpenObserve
services/nova-core/        The FastAPI brain
  app/
    main.py                FastAPI app: /health, /v1/chat/completions, /dashboard/*
    agent.py               LLM ↔ tools agent loop
    llm.py                 Ollama chat client
    identity.py            Channel identity → household user
    config.py              Env-based settings
    tools/                 Household capabilities (tasks, calendar, email) — Phase 5 stubs
```

## Build phases

| Phase | What | Status |
|------:|------|--------|
| 0 | Proxmox infra: GPU passthrough, Docker, NVIDIA toolkit | host setup |
| 1 | Coolify self-hosted CI/CD (git push-to-deploy) | host setup |
| 2 | Local runtime: Ollama + Postgres/pgvector | scaffolded |
| 3 | **Nova Core**: agent loop, identity, memory, OpenAI API | **scaffolded** |
| 4 | WhatsApp (Meta Cloud API) | pending |
| 5 | Household tools: tasks, CalDAV, Outlook/Graph email | stubs in place |
| 6 | Voice: HA Assist + Whisper/Piper, ESPHome, iPhone | compose wired |
| 7 | Proactive: briefings, reminders, better TTS | pending |
| 8 | Static LAN dashboard (calendar + tasks) | endpoints stubbed |

## Local development

```bash
cp .env.example .env          # then edit values
docker compose up -d
# Pull the model into the ollama container (first run):
docker compose exec ollama ollama pull qwen3:14b

# Smoke-test the brain:
curl -s localhost:8080/health
curl -s localhost:8080/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"user":"Ruben","messages":[{"role":"user","content":"add milk to the shopping list"}]}'
```

Tools currently return `[stub]` responses; Phase 5 replaces the bodies in
`services/nova-core/app/tools/` with real Postgres / CalDAV / Graph calls behind the same
function specs.

## Deployment

Deploys are git-driven via **Coolify** on the Nova AI VM (Phase 1). Push to `main` →
Coolify rebuilds and redeploys each service. Secrets are managed in Coolify, not in git.

**Closed feedback loop:** [ops/](./ops/) implements closed-loop incident management with
**Forgejo issues** ([git.7rb.nl/ruben/nova/issues](https://git.7rb.nl/ruben/nova/issues))
as the single incident queue — fed by OpenObserve alerts (logs/metrics via Vector →
`ops-bridge` webhook), deploy verification (`observe.sh`), and user-filed issues.
`triage.sh` picks up `auto-heal`-labeled issues and runs Claude Code headless (`heal.sh`)
to diagnose and commit fixes, reporting back as issue comments — supervised, review-gated,
or fully autonomous. See [ops/README.md](./ops/README.md).
