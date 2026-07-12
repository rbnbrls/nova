# Phase 18 Context: Security Hardening

## Source
ROADMAP.md Phase 18 goal + success criteria.

## Decisions
- Auth check already exists in main.py chat_completions using hmac.compare_digest. Verify it runs BEFORE user attribution is trusted (reorder if needed).
- ops-bridge app.py should use hmac.compare_digest for X-Bridge-Token instead of ==
- Error responses for auth failures should mimic the Phase 17 friendly fallback pattern (no internal details leaked)
- All 3 success criteria are clear — no additional decisions needed
