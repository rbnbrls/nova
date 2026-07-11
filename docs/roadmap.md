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

**Closed-loop SDLC & incident management (`ops/`):** **Forgejo issues**
(git.7rb.nl/ruben/nova) are the single incident queue, fed by three producers —
**OpenObserve alerts** (stack logs/metrics shipped via Vector; alerts hit the
`ops-bridge` webhook which dedups and files issues), **deploy failures**
(`observe.sh`), and **users** filing issues directly. `triage.sh` polls open
issues gated by the `auto-heal` label and runs **Claude Code headless**
(`heal.sh`: `claude -p`, constrained tool allowlist) to diagnose and commit
fixes on a heal branch, reporting back as issue comments (`fix-ready` /
`heal-failed`). `pipeline.sh` closes the deploy loop (deploy → observe → triage
→ redeploy, attempt-capped). Autonomy is opt-in per level: supervised →
review-gated → fully autonomous. See `ops/README.md`.

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

## Roadmap extensions (beyond Phase 8)

Goal check: Nova runs 24/7 for a household of **two people who each interact with it
individually** — so the extensions prioritize (A) an SDLC where Nova's quality is measured
and self-correcting, not just its uptime, and (B) features that make *per-person* use good:
knowing who is talking, keeping per-person context, and being proactive without being noisy.

### Track A — Agentic SDLC improvements

The `ops/` loop today closes the loop on **infra failures** (deploy broke, container
crashed). These items extend it to close the loop on **product failures** (Nova gave a
wrong/bad answer) and make unattended evolution safe.

#### A1 — Test harness & deploy gate
Pytest suite for nova-core (identity mapping, tool registry, agent loop with a mocked LLM,
webhook signature verification) + ops-bridge (dedup/fingerprint). Run in the container build
so a red suite fails the Coolify deploy; `heal.sh` must run the suite before committing a fix
(today it commits unverified). **Verify:** a deliberately broken commit never reaches `main`
deployed; a heal branch with failing tests is rejected.

#### A2 — Agent eval suite ("prompt CI")
Golden-conversation evals against the *real* local model: given "add milk to the shopping
list", assert `add_task` is called with the right args; cover date parsing ("Thursday 4pm"),
Dutch/English inputs, multi-tool turns, and refusal cases. Run on every change to
`SYSTEM_PROMPT`, tool specs, or `NOVA_MODEL` — this is the safety net that makes swapping
Qwen3-14B for anything else (open risk above) a measurable decision instead of vibes.
**Verify:** eval score reported per commit; a prompt regression blocks deploy.

#### A3 — Agent-run tracing & quality alerts
Structured trace per turn into OpenObserve (channel, user, latency, tokens, tool calls,
tool errors, iteration count, "got stuck" exits). Dashboards + alerts on tool-error rate
and p95 voice latency — these alerts flow into the existing ops-bridge → Forgejo path, so
a *quality* regression files an incident just like a crash does. **Verify:** forcing a tool
to error repeatedly produces a Forgejo issue with the offending traces attached.

#### A4 — User-feedback → incident loop
"Nova, that was wrong" (or a 👎 on WhatsApp) files a Forgejo issue with the redacted
transcript attached and becomes a candidate eval case for A2. This turns the two household
users into the QA team with zero friction, and connects bad answers to the same triage/heal
machinery that already handles crashes. **Verify:** a thumbs-down round-trips into an issue
containing enough context to reproduce.

#### A5 — Staging lane & model upgrades
Second compose profile (`nova-staging`, separate DB schema, same GPU) that Coolify deploys
first; promotion to prod requires A1 tests + A2 evals green. Use the same lane to benchmark
new Ollama models side-by-side (quality via A2, VRAM/latency via A3) before switching.
**Verify:** a model swap ships through staging with a before/after eval report.

#### A6 — Scheduled maintenance agent
Nightly headless Claude Code run (same guardrails as `heal.sh`): dependency/CVE bumps as
`fix-ready` branches, log-anomaly review, backup verification (restore a Postgres dump into
a scratch container and query it), disk/VRAM trend report. Findings are Forgejo issues —
humans stay in the merge path unless the autonomy level says otherwise. **Verify:** an
outdated dependency yields a green-tested bump branch overnight; a corrupted backup is
detected by the drill, not by a disaster.

### Track B — User-facing features

#### B1 — Speaker identity on voice
The two-person goal makes this the highest-leverage feature: WhatsApp attributes by phone
number, but voice currently can't tell Ruben from Méral. Add speaker ID (per-room satellite
default + voice-embedding identification, e.g. speaker verification on the Whisper audio) so
"add it to my list" resolves correctly hands-free. Fall back to asking ("For you, Méral?").
**Verify:** both users say "what's on *my* plan?" at the same satellite and get their own answers.

#### B2 — Per-person memory & privacy scopes
Use the `memories.user_id` column for real: `remember`/`forget` tools with a scope
(`private-to-me` vs `household`), retrieval filtered to requester + household. Private scope
means Nova can help Ruben plan Méral's surprise birthday dinner without leaking it in her
morning briefing. Include a memory browser on the dashboard (view/edit/delete what Nova
believes). **Verify:** a private memory never appears in the other user's answers or briefing.

#### B3 — Household coordination
Message relay ("tell Méral I'll be late" → her WhatsApp, attributed), recurring chores with
rotation and fair-share nudges ("it's your week for the bins"), and a first-class grocery
list (add-by-voice, auto-dedup, "what do we need?" at the shop) distinct from tasks.
**Verify:** a relayed message arrives on the other phone; a rotating chore alternates assignee.

#### B4 — Proactivity that respects attention (extends Phase 7)
Per-user briefing time/channel/content preferences; quiet hours; calendar-aware delivery
(don't interrupt a meeting); deadline escalation (gentle → day-of → overdue on the
dashboard). Every proactive push is per-person, not broadcast. **Verify:** the same morning
produces two different briefings at two different times.

#### B5 — Deeper email & calendar intelligence
Email → action extraction: an invoice becomes a task with a due date, an invitation becomes
a proposed event ("shall I add it?"), a parcel notification becomes a heads-up. Calendar
conflict detection and travel-time warnings on event creation; birthday/recurring-date
tracking from memory. Reply drafting stays local (draft via local LLM, send via Graph only
on explicit confirm). **Verify:** a real invoice email yields a task with the correct due date.

#### B6 — Home Assistant as a tool, not just a channel
Nova already sits behind HA's voice pipeline; add an HA REST tool so Nova can *act*: lights,
thermostat, presence ("is Méral home?"), and presence-aware behavior (suppress "leave now"
nudges when already gone; route voice answers to the room the speaker is in). **Verify:**
"turn off the living-room lights when my meeting starts" works end-to-end.

#### B7 — Write-action confirmations & audit trail
Confirm-before-write for destructive/external actions (delete event, send email) tuned
per channel (voice confirms verbally, WhatsApp uses a quick-reply button), plus an "activity
feed" ("what did you change today?") on the dashboard and as a query. Builds the trust needed
to grant Nova more autonomy later. **Verify:** every mutating tool call is visible in the feed.

#### B8 — Paper & photo intake
WhatsApp image → local vision model (or OCR) → structured action: a photo of a school
letter becomes a summarized event + task; a warranty receipt gets filed into searchable
household docs. All processing stays on the GPU per the privacy boundary. **Verify:** a
photographed letter with a date in it produces a correct proposed calendar event.

### Suggested sequencing
A1 → A3 land **before Phase 4/5 ship real integrations** (tests and traces are cheap now,
expensive to retrofit). A2 lands with Phase 5 (first real tool behaviors to pin down).
B1/B2 follow Phase 6 (voice) since they define the individual-user experience; B4/B7 extend
Phase 7; B3/B5/B6/B8 are demand-driven after that. A4–A6 harden the loop once real usage exists.

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
