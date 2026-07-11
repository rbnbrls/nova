# Codebase Concerns

**Analysis Date:** 2026-07-11

## Tech Debt

**Tool stubs return fake data (Phase 5 not yet implemented):**
- Issue: `add_task`, `list_tasks`, `complete_task` (`services/nova-core/app/tools/tasks.py`), `list_events`, `create_event` (`services/nova-core/app/tools/calendar.py`), and `list_recent_emails` (`services/nova-core/app/tools/email.py`) are all stubs that return canned strings like `"[stub] Added task '{title}' for {assignee}."` without touching Postgres, CalDAV, or Microsoft Graph.
- Files: `services/nova-core/app/tools/tasks.py:34,53,70`, `services/nova-core/app/tools/calendar.py:23,42`, `services/nova-core/app/tools/email.py:23`
- Impact: The LLM agent will confidently tell users tasks/events were created when nothing was persisted. If deployed as-is, this is silent data loss disguised as success.
- Fix approach: Implement the Phase 5 Postgres-backed tool bodies against the schema in `infra/postgres/init/01_schema.sql`; wire calendar/email to CalDAV and Microsoft Graph respectively. No Postgres client (e.g. `asyncpg`) is even present in `services/nova-core/requirements.txt` yet.

**Dashboard endpoints are stubs:**
- Issue: `GET /dashboard/tasks` and `GET /dashboard/events` always return empty lists.
- Files: `services/nova-core/app/main.py:46-55`
- Impact: Any dashboard UI built against these endpoints will show a permanently empty state.
- Fix approach: Wire to the same Postgres queries as the tools once Phase 5 lands.

**No database layer exists despite schema being defined:**
- Issue: `infra/postgres/init/01_schema.sql` defines `users`, `tasks`, `memories`, `messages` tables with pgvector support, but no Python code in `services/nova-core/app/` ever connects to Postgres. `config.py` computes a `database_url` property that is unused.
- Files: `services/nova-core/app/config.py:30-35`, `infra/postgres/init/01_schema.sql`
- Impact: Long-term memory (`memories` table) and conversation history (`messages` table) are schema-only; the agent has no persistence, so `history` is only ever what the caller passes in per-request (see below).
- Fix approach: Add an async Postgres client, implement memory retrieval/embedding writes, and persist message history server-side rather than relying on caller-supplied history.

**Conversation history is caller-supplied, not persisted:**
- Issue: `run_agent` in `services/nova-core/app/agent.py:22-30` takes `history` as a parameter derived from `req.messages[:-1]` in `main.py:32`. There is no server-side session/history store, so every channel integration (WhatsApp, voice, HA) must independently track and resend the entire conversation each turn.
- Files: `services/nova-core/app/agent.py:22-30`, `services/nova-core/app/main.py:28-40`
- Impact: No cross-channel memory; a WhatsApp conversation and a voice conversation with the same user won't share context. Also unbounded growth of client-side history with no truncation policy.
- Fix approach: Persist messages to the `messages` table keyed by `(user_id, channel)` and load recent history server-side.

## Known Bugs

**No max-history truncation before hitting the LLM:**
- Symptoms: `run_agent` appends `history` unconditionally to the message list sent to Ollama; there's no token/length cap.
- Files: `services/nova-core/app/agent.py:27-30`
- Trigger: A long-running conversation (e.g. one channel accumulating turns) sent as `history` will grow the request payload indefinitely, eventually exceeding the model's context window or ballooning latency.
- Workaround: None currently; caller must self-limit history size.

**Tool argument filtering silently drops unknown/malformed args:**
- Symptoms: `Tool.run` (`services/nova-core/app/tools/base.py:32-41`) filters `arguments` down to only the function's declared parameters via `sig.parameters`, silently ignoring anything the LLM passes that doesn't match. Bad LLM tool calls (e.g. wrong param name) won't error — they'll just call the function with fewer args than intended, likely producing a wrong-but-plausible tool result.
- Files: `services/nova-core/app/tools/base.py:32-41`
- Trigger: LLM tool-call arguments don't exactly match the declared JSON schema, e.g. `{"name": "..."}` instead of `{"title": "..."}` for `add_task`.
- Workaround: None; would benefit from raising/logging a warning when dropped keys are non-empty.

## Security Considerations

**No authentication on the primary chat API:**
- Risk: `POST /v1/chat/completions` (`services/nova-core/app/main.py:28-40`) has no auth check — anyone who can reach `nova-core:8080` can chat as any `user` (household member spoofing is trivial via the `user` field on `ChatCompletionRequest`).
- Files: `services/nova-core/app/main.py:28-40`, `services/nova-core/app/models.py:19-24`
- Current mitigation: Caddyfile (`Caddyfile:5-17`) restricts the dashboard/API route to a LAN-only `nova.local` site block, and the WhatsApp webhook route (commented out, `Caddyfile:19-26`) is the only path meant to be tunneled externally. This is "security by network topology," not application-level auth.
- Recommendations: Add a shared-secret or per-channel auth header check in `main.py` before trusting the `user` field, especially once the WhatsApp webhook route is uncommented and exposed via Cloudflare Tunnel.

**`ops-bridge` webhook auth is a single static bearer token compared with `!=`:**
- Risk: `services/ops-bridge/app.py:69` compares `x_bridge_token != BRIDGE_TOKEN` using Python's `!=`, which is not constant-time, making it theoretically vulnerable to timing attacks (low practical risk given deployment is self-hosted, but worth noting for a service that creates Forgejo issues with a privileged token).
- Files: `services/ops-bridge/app.py:64-70`
- Current mitigation: Requires `BRIDGE_TOKEN` env var to be set at all (empty token always rejects, `services/ops-bridge/app.py:69`).
- Recommendations: Use `hmac.compare_digest` for the token comparison.

**Forgejo/Coolify/Proxmox API tokens live in plaintext env files by design:**
- Risk: `ops/config.env`, `ops/secrets/infra.env`, and `.env` hold `FORGEJO_TOKEN`, `COOLIFY_API_TOKEN`, `PROXMOX_API_TOKEN_SECRET` in plaintext on disk (only `.example` variants are committed, per `.gitignore` presumably, but the pattern is inherently secret-on-disk).
- Files: `ops/config.env.example`, `ops/secrets/infra.env.example`
- Current mitigation: `.example` files are the only ones tracked in git; real files are gitignored.
- Recommendations: Acceptable for a single-operator self-hosted homelab; if scope grows (more users/operators), move to a secret manager.

**Proxmox audit script defaults to insecure TLS:**
- Risk: `ops/provision/audit-proxmox.sh:31` defaults `PROXMOX_API_INSECURE=true`, disabling TLS certificate verification (`curl -k`) unless explicitly overridden.
- Files: `ops/provision/audit-proxmox.sh:30-31`
- Current mitigation: Script is read-only and intended for one-time infra audit on a private network.
- Recommendations: Low priority given script scope, but flip the default to `false` once Proxmox has a real cert.

**Self-healing pipeline can autonomously push to `main`:**
- Risk: When `HEAL_AUTO_PUSH=true` and `HEAL_PUSH_TO_MAIN=true`, `ops/heal.sh:80-86` has Claude Code (headless, `--permission-mode acceptEdits`) commit a fix and the script itself merges to `main` and pushes without human review, re-triggering a production deployment.
- Files: `ops/heal.sh:30-59,80-86`, `ops/pipeline.sh:41-48`
- Current mitigation: Both flags default to `false` in `ops/config.env.example:29-30` — fully autonomous mode is opt-in and explicitly flagged "use with care" in the example config comment.
- Recommendations: Keep both flags off in production until the heal loop has a track record; consider requiring a second human approval gate (e.g. required PR review) even when auto-push is enabled.

**Heal loop's Claude invocation has broad file-write access:**
- Risk: `ops/heal.sh:52-58` grants `Read,Grep,Glob,Edit,Write,Bash(git ...)` tools with `--permission-mode acceptEdits`, meaning the headless agent can edit/write any file in the repo while diagnosing a production incident, with no scoped allowlist of directories.
- Files: `ops/heal.sh:52-58`
- Current mitigation: Runs on a clean working tree only (`ops/heal.sh:18`), on an isolated `heal-<timestamp>` branch, and pushing is gated (see above).
- Recommendations: Acceptable given the isolated branch + review gate, but note the prompt explicitly instructs "do not refactor" — this is enforced by prompt only, not tooling.

## Performance Bottlenecks

**Ollama call has no retry/backoff and a fixed 120s timeout:**
- Problem: `llm.chat` (`services/nova-core/app/llm.py:9-30`) uses a flat `httpx.AsyncClient(timeout=120)` with no retry logic; a slow or transiently-failing local Ollama instance will hang the whole `/v1/chat/completions` request for up to 120s before failing outright (the exception isn't even caught in `agent.py` or `main.py`, so it will surface as a 500).
- Files: `services/nova-core/app/llm.py:27-30`, `services/nova-core/app/agent.py:35`
- Cause: No timeout tuning per call type, no retry/circuit-breaker.
- Improvement path: Add bounded retries with backoff for transient failures, and catch/translate `httpx` errors into a graceful chat response instead of a raw 500.

**Agent loop can make up to 6 sequential LLM calls per user turn:**
- Problem: `MAX_TOOL_ITERATIONS = 6` in `services/nova-core/app/agent.py:11` means a single chat turn can serially call the local LLM (each up to 120s) up to 6 times if the model keeps requesting tools without producing a final answer.
- Files: `services/nova-core/app/agent.py:11,34-51`
- Cause: No hard wall-clock budget for the whole turn, only an iteration count.
- Improvement path: Add an overall timeout/budget across the full tool-calling loop, not just per-call.

## Fragile Areas

**WhatsApp user mapping is parsed once at import time from env:**
- Files: `services/nova-core/app/identity.py:20-31`
- Why fragile: `_WHATSAPP_USERS` is built once at module load (`_parse_whatsapp_map()` called at import time, `identity.py:31`). Changing `NOVA_WHATSAPP_USERS` requires a process restart; there's no reload mechanism. Also silently drops malformed entries (missing `:`) with no logging.
- Safe modification: When adding a new household member, ensure the process restarts; consider validating the env var at startup and logging parse failures rather than silently skipping them.
- Test coverage: No tests found anywhere in the repo (see below) — this parsing logic is entirely unverified.

**No test suite exists in the repository:**
- Files: repo-wide — no `tests/`, `*_test.py`, `test_*.py`, or `pytest`/test framework in either `services/nova-core/requirements.txt` or `services/ops-bridge/requirements.txt`.
- Why fragile: All logic (agent loop, tool registration/dispatch, identity mapping, ops-bridge webhook dedup/fingerprinting) is unverified by automated tests. The self-healing loop (`ops/heal.sh`) relies on `python -m compileall` as its only "verification" step (`ops/heal.sh:41-42`), which only checks syntax validity, not behavior.
- Safe modification: Any change to `agent.py`, `tools/base.py`, or `ops-bridge/app.py` risks silent regressions.
- Test coverage: None.

**`ops-bridge` label-ID cache is a module-level mutable dict with no invalidation:**
- Files: `services/ops-bridge/app.py:38,41-52`
- Why fragile: `_label_ids` is cached forever once populated; if labels are renamed/deleted on the Forgejo repo after the service starts, `_resolve_label_ids` will keep using stale IDs or keep re-fetching for names that will never resolve (only re-fetches for `missing` names not yet in the cache, so a renamed label after first successful lookup is never re-checked).
- Safe modification: Restart `ops-bridge` after any Forgejo label changes, or add TTL/invalidation to the cache.
- Test coverage: None.

**Alert dedup fingerprint is coarse (`alert_name` + `stream` only):**
- Files: `services/ops-bridge/app.py:55-56`
- Why fragile: `_fingerprint` hashes only `alert_name|stream`, ignoring severity, host, or any other alert dimension. Two distinct incidents on the same stream with the same alert name will collapse into one Forgejo issue thread even if unrelated in time/cause.
- Safe modification: If richer alert payloads are added later, consider including more fields (e.g. host, severity) in the fingerprint, or accept the current coarse grouping as intentional (per the module docstring's "closed-loop incident intake" design).
- Test coverage: None.

## Scaling Limits

**Single-node Docker Compose, single Postgres, single Ollama with GPU passthrough:**
- Current capacity: Entire stack (`docker-compose.yml`) is designed for one household on one VM with a single GPU; `ollama` and `whisper` both request `capabilities: [gpu]` with `count: all` — no support for multiple GPUs or horizontal scaling.
- Limit: Fine for the stated single-household use case; would need a fundamentally different architecture (managed LLM API, connection pooling, multi-tenant schema) to serve multiple households.
- Scaling path: Not a near-term concern given the project's explicit household-assistant scope (`README.md`), but worth flagging if scope ever expands.

## Dependencies at Risk

**`requirements.txt` pins exact versions with no lockfile or automated update mechanism:**
- Risk: `services/nova-core/requirements.txt` and `services/ops-bridge/requirements.txt` pin exact versions (`fastapi==0.115.6`, `httpx==0.28.1`, etc.) but there's no `requirements-dev.txt`, `poetry.lock`, or Dependabot/Renovate config detected.
- Impact: Security patches for FastAPI/httpx/pydantic won't be picked up automatically; manual bumping required.
- Migration plan: Add a dependency update bot (Renovate/Dependabot) once the repo is hosted somewhere that supports it (currently Forgejo self-hosted per `ops/issue.sh`), or adopt a periodic manual review cadence.

**`ollama/ollama:latest`, `timberio/vector:latest-alpine`, and Wyoming images use `:latest` tags:**
- Risk: `docker-compose.yml:40,55,71,81` pin `ollama:latest`, `rhasspy/wyoming-whisper:latest`, `rhasspy/wyoming-piper:latest`, and `timberio/vector:latest-alpine` — none are version-pinned.
- Impact: A `docker compose pull` at any point can introduce breaking changes with no warning, and deployments become non-reproducible (today's `ollama:latest` may differ from tomorrow's).
- Migration plan: Pin explicit version tags for all four images once the stack stabilizes past early development.

## Missing Critical Features

**No error handling around the agent's LLM/tool calls at the API boundary:**
- Problem: `main.py:35` calls `await run_agent(...)` with no try/except; any unhandled exception (Ollama down, tool exception not caught by `Tool.run`, JSON parse failure on `args = json.loads(...)` in `agent.py:47`) will surface as a raw FastAPI 500 with a stack trace, not a graceful user-facing message.
- Blocks: Production-grade reliability for a household-facing assistant; a WhatsApp or voice user would see a broken response instead of "Nova is having trouble right now."
- Fix approach: Wrap `run_agent` invocation in `main.py` with error handling that returns a friendly fallback message and logs the exception.

**No persisted conversation/memory despite schema existing (`messages`, `memories` tables unused) — see Tech Debt above.**

**No authentication/authorization layer for the WhatsApp webhook route (not yet implemented):**
- Problem: `Caddyfile:19-26` shows the intended WhatsApp webhook route is commented out and not yet built; when it lands, it needs to verify WhatsApp Business API signatures to avoid accepting forged messages from the public Cloudflare Tunnel endpoint.
- Blocks: Safe external exposure of the chat endpoint.
- Fix approach: Implement webhook signature verification when the WhatsApp integration (Phase 4 per code comments) is built.

## Test Coverage Gaps

**Entire codebase has zero automated tests:**
- What's not tested: Agent loop (`services/nova-core/app/agent.py`), tool registration/dispatch (`services/nova-core/app/tools/base.py`), identity resolution (`services/nova-core/app/identity.py`), ops-bridge webhook handling/dedup (`services/ops-bridge/app.py`), all ops shell scripts (`ops/*.sh`).
- Files: repo-wide.
- Risk: Any refactor or dependency bump could silently break tool-calling, user attribution, or the incident-intake webhook with no automated signal.
- Priority: High — especially for `tools/base.py`'s argument-filtering logic and `identity.py`'s WhatsApp number parsing, both of which have subtle edge-case behavior (silent drops) that are easy to get wrong.

---

*Concerns audit: 2026-07-11*
