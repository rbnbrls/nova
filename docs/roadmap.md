# Nova — Build Roadmap

> Canonical roadmap for the Nova household assistant. Mirrors the approved plan.

## Decisions locked in
- **LLM brain: fully local / air-gapped** — reasoning model runs on the GPU; no prompts/content to a cloud LLM.
- **Calendar: self-hosted CalDAV** (HA local calendar or Radicale/Nextcloud).
- **WhatsApp: Meta Cloud API** (official).
- **Deployment: self-hosted CI/CD via Coolify** (git-driven).
- **Existing stack: Home Assistant already running.**

**Privacy boundary:** the model and all household data stay local. Only two channels reach
external providers by nature — WhatsApp Cloud API (Meta) and the shared Outlook mailbox
(Microsoft Graph). Reasoning and storage never leave the box.

## Phases

### Phase 0 — Infrastructure foundation
GPU-capable container host + secure inbound path. Nova AI VM, PCIe passthrough of the RTX 2000
Blackwell (VFIO), NVIDIA drivers + Container Toolkit, Docker. Static IPs/DNS. Caddy + Cloudflare
Tunnel for the WhatsApp webhook. **Verify:** `docker run --gpus all … nvidia-smi` sees the GPU.

### Phase 1 — Deployment platform & CI/CD (Coolify)
Install Coolify on the Nova AI VM. Connect the Nova git repo; each service is a Coolify
resource with secrets managed in Coolify. Push-to-deploy on `main`, health checks, rollbacks.
GPU containers run with `--gpus` passthrough. **Verify:** a commit auto-redeploys; rollback works.

**Closed-loop SDLC (`ops/`):** deployments are code-triggered and self-observing —
`deploy.sh` drives Coolify via API, `observe.sh` verifies health and writes structured
incident reports on failure, and `heal.sh` feeds incidents to **Claude Code headless**
(`claude -p`, constrained tool allowlist) to diagnose and commit fixes on a heal branch;
`pipeline.sh` closes the loop (deploy → observe → heal → redeploy, attempt-capped).
Autonomy is opt-in per level: supervised → review-gated → fully autonomous. See `ops/README.md`.

### Phase 2 — Local AI runtime
Ollama serving a ~14B tool-calling model (Qwen3-14B candidate). Postgres + pgvector. Deployed via
Coolify. **Verify:** Ollama returns a tool-call; model + Whisper coexist in VRAM.

### Phase 3 — Nova Core
FastAPI OpenAI-compatible `/v1/chat/completions`. Agent loop with native tool-calling. Multi-user
identity (Ruben/Méral/household). Short-term history + pgvector long-term memory. **Verify:** chat
endpoint round-trips a stubbed tool.

### Phase 4 — WhatsApp (Meta Cloud API)
Dedicated business number, Meta app, permanent token. Webhook → Nova Core (signature verify,
sender→user, reply via send API). **Verify:** messages from both phones round-trip with attribution.

### Phase 5 — Household data tools
Tasks (Postgres, attributed, deadlines). CalDAV calendar (read/write). MS Graph email (Mail.Read on
shared mailbox; local LLM classifies "important"). **Verify (via WhatsApp):** calendar/task/email
queries return correct results.

### Phase 6 — Voice channel
HA Assist: Wyoming faster-whisper (GPU) STT + Piper TTS; HA conversation agent → Nova Core endpoint.
ESPHome satellite(s) with a custom "Nova" wake word. iPhone via HA Companion Assist. **Verify:**
spoken query → spoken answer on satellite and phone.

### Phase 7 — Proactive behavior & polish
Scheduler: morning briefing, reminders, important-email push. Piper → Kokoro voice upgrade.
Per-room context, memory tuning, write-action confirmations. Backups, monitoring, snapshots.

### Phase 8 — Static household dashboard
LAN-only static SPA served by Caddy (no external assets). Calendar view (`GET /dashboard/events`)
+ active-tasks-with-deadlines overview (`GET /dashboard/tasks`), grouped by assignee, overdue
flagged. Read-only, auto-refresh. **Verify:** dashboard matches what WhatsApp/voice report.

## End-to-end acceptance (after Phase 6)
1. WhatsApp: "add 'book dentist' and put a slot Thursday 4pm" → task + event created.
2. Voice: "what's on our plan tomorrow?" → Nova speaks the agenda.
3. Important email arrives → proactive WhatsApp summary (Phase 7).
4. LAN dashboard shows the same events + active tasks with deadlines (Phase 8).

## Open risks
- Custom "Nova" wake word needs training; start with a stock wake word.
- Shared-mailbox Graph permissions (app vs delegated + admin consent).
- 14B tool-calling reliability — validate early (Phase 2); fall back to 8B/vLLM if needed.
- CalDAV backend choice (HA built-in vs Radicale/Nextcloud) at Phase 5.
- Coolify + GPU passthrough — confirm `--gpus` works; else run GPU containers as raw Docker.
