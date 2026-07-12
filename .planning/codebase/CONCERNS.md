# Codebase Concerns

**Analysis Date:** 2026-07-12 (Refreshed after v2.0 milestone close)

## Tech Debt

**Conversation history is caller-supplied, not persisted:**
- Issue: `run_agent` in `services/nova-core/app/agent.py` takes `history` as a parameter derived from the incoming request.
- Impact: No cross-channel memory; a WhatsApp conversation and a voice conversation with the same user won't share context.
- Fix approach: Persist messages to the `messages` table keyed by `(user_id, channel)` and load recent history server-side.

## Known Bugs

**Tool argument filtering silently drops unknown/malformed args:**
- Symptoms: `Tool.run` filters `arguments` down to only the function's declared parameters, silently ignoring anything the LLM passes that doesn't match. Bad LLM tool calls won't error.
- Trigger: LLM tool-call arguments don't exactly match the declared JSON schema.
- Workaround: None; would benefit from raising/logging a warning when dropped keys are non-empty.

## Security Considerations

**Forgejo/Coolify/Proxmox API tokens live in plaintext env files by design:**
- Risk: `ops/config.env`, `ops/secrets/infra.env`, and `.env` hold API tokens in plaintext on disk.
- Current mitigation: `.example` files are the only ones tracked in git; real files are gitignored.
- Recommendations: Acceptable for a single-operator self-hosted homelab; if scope grows, move to a secret manager.

**Proxmox audit script defaults to insecure TLS:**
- Risk: Defaults `PROXMOX_API_INSECURE=true`, disabling TLS certificate verification.
- Recommendations: Low priority given script scope, but flip the default to `false` once Proxmox has a real cert.

**Self-healing pipeline can autonomously push to `main`:**
- Risk: When `HEAL_AUTO_PUSH=true` and `HEAL_PUSH_TO_MAIN=true`, the heal loop pushes without human review.
- Recommendations: Keep both flags off in production until the heal loop has a track record.

**Heal loop's Claude invocation has broad file-write access:**
- Risk: Grants broad tools with `--permission-mode acceptEdits`, meaning the headless agent can edit/write any file in the repo.
- Recommendations: Acceptable given the isolated branch + review gate, but note the prompt explicitly instructs "do not refactor" — this is enforced by prompt only, not tooling.

## Fragile Areas

**WhatsApp user mapping is parsed once at import time from env:**
- Why fragile: `_WHATSAPP_USERS` is built once at module load. Changing `NOVA_WHATSAPP_USERS` requires a process restart.
- Safe modification: When adding a new household member, ensure the process restarts.

**`ops-bridge` label-ID cache is a module-level mutable dict with no invalidation:**
- Why fragile: `_label_ids` is cached forever once populated.
- Safe modification: Restart `ops-bridge` after any Forgejo label changes, or add TTL/invalidation to the cache.

**Alert dedup fingerprint is coarse (`alert_name` + `stream` only):**
- Why fragile: `_fingerprint` hashes only `alert_name|stream`, ignoring severity, host, or any other alert dimension.
- Safe modification: Accept current coarse grouping, or include more fields if richer payloads are added.

## Dependencies at Risk

**`requirements.txt` pins exact versions with no lockfile or automated update mechanism:**
- Risk: Pin exact versions with no `requirements-dev.txt`, `poetry.lock`, or Dependabot/Renovate.
- Migration plan: Add a dependency update bot once hosted appropriately.

**Images use `:latest` tags:**
- Risk: `docker-compose.yml` pins `latest` for ollama, wyoming, and vector.
- Migration plan: Pin explicit version tags for all images once the stack stabilizes.

---
*Concerns audit: 2026-07-12*
