# Phase 40: admin panel page - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a separate admin page at `/admin` (serving `/static/admin.html`) that shows read-only system health and channel status for the Nova household assistant. The page displays green/red health indicators with key details per service (Ollama model, Postgres connectivity, CalDAV/HA/email reachability) and WhatsApp/Telegram linked/unlinked status per user. Status updates push via SSE. No authentication — LAN-only trust, same as the existing dashboard. No visible link from the dashboard — accessed by typing `/admin` directly.

</domain>

<decisions>
## Implementation Decisions

### Panel Scope
- **D-01:** System status + channel link status only. No audit log viewer, no config viewer, no memory management — those are out of scope for Phase 40.
- **D-02:** Health indicators with key details per service: Ollama (model name qwen3:14b, ready/not), Postgres (connected, table counts), CalDAV (reachable, URL), Home Assistant (reachable, URL), email IMAP (connected, configured address). Ping-style checks with contextual details.
- **D-03:** Channel link status: WhatsApp and Telegram linked/unlinked per user (Ruben, Méral). Reuse existing data from the preferences/linking endpoints — just surface it on the admin page.
- **D-04:** No write actions — read-only monitoring. No restart, no config editing, no memory clearing. This is a status board, not a control panel.

### Page Architecture
- **D-05:** Separate HTML page at `/static/admin.html` with a `/admin` route redirect (mirrors the `/dashboard` → `/static/index.html` pattern in `main.py:281-283`).
- **D-06:** Shared `style.css` (reuse glass-panel, button, badge, grid styles), separate `admin.js` (admin-specific logic only — do not add to `app.js`).
- **D-07:** No visible link from the household dashboard. The admin page is accessed by typing `/admin` directly. No footer link, no header link — intentional obscurity on top of LAN trust.

### Access Control
- **D-08:** No authentication — LAN-only trust, same as the existing dashboard. The household is 2 people on a private network; network access is the security boundary.
- **D-09:** No discoverability — the admin URL is not advertised on the dashboard. Must know `/admin` to access.

### Status Refresh
- **D-10:** SSE real-time push for status updates. Extend the existing `/dashboard/stream` SSE pattern or create a new `/admin/stream` endpoint that pushes health check results on an interval.

### the agent's Discretion
- Exact layout of the admin page (card grid, list, sections) — keep the glass-panel aesthetic consistent with the dashboard.
- SSE interval for health checks (30s-60s range is reasonable; balance freshness vs. load).
- Whether to create a new `/admin/stream` SSE endpoint or extend `/dashboard/stream` with admin events.
- How to structure the backend health-check endpoint (single `/admin/status` that checks all services, or individual per-service endpoints).
- Error/loading states for services that are unreachable.
- Whether to show a "Back to Dashboard" link on the admin page (recommended for usability, but not a hard requirement).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Dashboard Frontend (existing patterns to follow)
- `services/nova-core/static/index.html` — Existing dashboard HTML. Glass-panel cards, grid layout, status indicator pattern.
- `services/nova-core/static/style.css` — Shared CSS. `.dashboard-card.glass-panel`, `.btn`, `.badge`, `.pulse-dot`, `.status-indicator` styles to reuse.
- `services/nova-core/static/app.js` — Existing dashboard JS. SSE event source pattern, fetch API calls, update functions. Reference for admin.js patterns.

### Backend (endpoints to extend/reference)
- `services/nova-core/app/main.py` — FastAPI routes. `/dashboard` redirect pattern (line 281-283), `/health` endpoint (line 140-142), `/dashboard/stream` SSE generator (line 286+), `/dashboard/audit` endpoint (line 253-278). Add `/admin` redirect and `/admin/status` or `/admin/stream` here.
- `services/nova-core/app/config.py` — Settings singleton. Contains all service URLs and config values the admin page will display (Ollama URL, model name, Postgres, CalDAV, HA, email, Telegram, WhatsApp).
- `services/nova-core/app/llm.py` — `is_ready()` async function for Ollama health check. Reuse for admin status.
- `services/nova-core/app/db.py` — Database pool. Reuse `get_pool()` for Postgres connectivity check and table counts.

### Architecture & Patterns
- `.planning/codebase/ARCHITECTURE.md` — System overview, component responsibilities, data flow patterns.
- `.planning/codebase/STACK.md` — Tech stack reference.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `style.css` — `.glass-panel`, `.dashboard-card`, `.badge`, `.badge-accent`, `.pulse-dot`, `.status-indicator`, `.btn`, `.btn-primary`, `.btn-success` classes. The admin page should reuse these for visual consistency.
- `llm.is_ready()` — async function that checks Ollama health. Already used by `/health` endpoint.
- `db.get_pool()` — asyncpg pool acquisition. Can run a simple `SELECT 1` or table count query for Postgres status.
- `/dashboard/stream` SSE pattern — `event_generator()` function that yields SSE events. Template for admin SSE endpoint.
- `/dashboard` redirect pattern — `RedirectResponse(url="/static/index.html")`. Mirror for `/admin` → `/static/admin.html`.
- Settings modal user selector pattern (Ruben/Méral tabs) — reuse for channel status per-user display.

### Established Patterns
- Dashboard API calls use `fetch()` with JSON — consistent across all dashboard endpoints.
- SSE uses `EventSource` on the frontend, `StreamingResponse` with `text/event-stream` on the backend.
- FastAPI routes are `async def` with direct DB queries via asyncpg.
- Static files served via `StaticFiles` mount — `admin.html` will be served automatically from `/static/`.
- Config is read-only via `settings` singleton — display values, don't edit.

### Integration Points
- `app/main.py` — Add `GET /admin` redirect route and `GET /admin/status` or `GET /admin/stream` SSE endpoint.
- `static/admin.html` — New file. Admin page HTML with glass-panel cards for each service.
- `static/admin.js` — New file. SSE event source, status rendering, channel link status fetching.
- `style.css` — May need minor additions for admin-specific layout (service status grid, health indicator styles).
- Existing `/api/preferences` endpoint — can be reused to fetch WhatsApp/Telegram link status per user.

</code_context>

<specifics>
## Specific Ideas

- The admin page should feel like a natural extension of the dashboard — same glass-panel aesthetic, same fonts, same spacing.
- Health indicators should be immediately scannable: green dot = healthy, red dot = down, with the service name and key detail visible at a glance.
- Channel status should show per-user linked/unlinked — same visual pattern as the settings modal but in a read-only card format.

</specifics>

<deferred>
## Deferred Ideas

- Audit log viewer with filtering — belongs in a future phase (the `/dashboard/audit` endpoint and activity feed already exist on the main dashboard).
- Config viewer (read-only display of all env settings) — future phase.
- Memory management (view/clear long-term memories per user) — future phase; adds write actions.
- Write actions (restart Ollama, run migrations, clear cache) — future phase; significantly increases backend complexity.
- Admin authentication / multi-user admin roles — not needed for a 2-person LAN household.
- Webhook health diagnostics (last received timestamp per channel) — future enhancement.

</deferred>

---

*Phase: 40-admin-panel-page*
*Context gathered: 2026-07-13*
