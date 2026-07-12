# Phase 36 Context: Write-Action Audit Trail

## Source
ROADMAP.md Phase 36 goal + success criteria.

## Decisions

### Feed Format
- Dashboard table (scrolling activity feed)
- No natural-language query support initially
- Accessible at `/dashboard/audit` endpoint with SSE updates

### What's Recorded
- Every mutating tool call: create_event, complete_task, add_task, send_email (future)
- Timestamp, user, tool name, action summary, status
- Non-destructive reads and queries excluded
- Extends the write confirmation gate (Phase 8) — if a tool triggers confirmation, the audit record includes whether it was confirmed or denied

### Implementation
- New DB table `audit_log` (or extend existing tracking)
- Dashboard endpoint: `GET /dashboard/audit` returns last N entries
- Auto-prune entries older than 90 days
- Follow existing dashboard FastAPI patterns

## Deferred Ideas
- Natural-language query ("what changed today?") — future enhancement
