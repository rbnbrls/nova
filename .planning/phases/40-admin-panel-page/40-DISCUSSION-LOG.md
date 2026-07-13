# Phase 40: admin panel page - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-13
**Phase:** 40-admin-panel-page
**Areas discussed:** Panel scope, Page architecture, Access control

---

## Panel scope

### Q1: What should the admin panel show in Phase 40?

| Option | Description | Selected |
|--------|-------------|----------|
| System status + channels | Health checks (Ollama, Postgres, CalDAV, HA, email) + channel status (WhatsApp/Telegram linked, voice rooms). Read-only monitoring. | ✓ |
| Status + audit log viewer | Above + filterable audit log viewer (already have /dashboard/audit endpoint). | |
| Status + audit + config view | Above + read-only config viewer (model name, env settings, feature toggles). | |
| Full: status + audit + config + memory | All of the above + memory management (view/clear long-term memories per user). | |

**User's choice:** System status + channels
**Notes:** Simplest scope — read-only monitoring only.

### Q2: How deep should the system status go?

| Option | Description | Selected |
|--------|-------------|----------|
| Health indicators only | Green/red status indicators for each service. Simple ping-style checks. | |
| Health + key details | Above + model name, DB table counts, HA URL, email address configured. | ✓ |
| Health + details + system log | Above + mini audit feed focused on system events. | |

**User's choice:** Health + key details
**Notes:** More informative without being a full dashboard.

### Q3: What channel information should be shown?

| Option | Description | Selected |
|--------|-------------|----------|
| Channel link status | Linked/unlinked status for WhatsApp and Telegram per user. | ✓ |
| Channel status + voice rooms | Above + voice room configuration. | |
| Full channel diagnostics | Above + webhook health (last received timestamp). | |

**User's choice:** Channel link status
**Notes:** Reuse existing data from settings modal — just surface it on the admin page.

### Q4: How should status refresh?

| Option | Description | Selected |
|--------|-------------|----------|
| Poll every 30s | Auto-refresh via polling. Simple. | |
| SSE real-time push | Extend existing /dashboard/stream to push status updates. Real-time. | ✓ |
| Manual refresh button | No auto-refresh — click to refresh. | |

**User's choice:** SSE real-time push
**Notes:** Reuse existing SSE pattern.

---

## Page architecture

### Q1: How should the admin panel be structured relative to the existing dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate page (/admin) | Separate HTML page at /static/admin.html with /admin route redirect. | ✓ |
| Section on dashboard | New full-width section on the existing dashboard. | |
| Tab toggle on dashboard | Tab/view toggle at the top of the existing dashboard. | |

**User's choice:** Separate page (/admin)
**Notes:** Clean separation from the household dashboard.

### Q2: Should the admin page share frontend assets with the dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared CSS, separate JS | Reuse style.css, new admin.js. Shared CSS keeps aesthetic consistent. | ✓ |
| Shared CSS + shared JS | Shared style.css + shared app.js. Less file duplication. | |
| Fully separate files | Separate admin.css + admin.js. Maximum isolation. | |

**User's choice:** Shared CSS, separate JS
**Notes:** Keep CSS shared for visual consistency, separate JS for clean code.

### Q3: How should users navigate between dashboard and admin page?

| Option | Description | Selected |
|--------|-------------|----------|
| Header link on dashboard | Small 'Admin' link/button in the dashboard header. | |
| Footer link | Footer link at the bottom of the dashboard page. | ✓ (initially) |
| No visible link | No link — must type /admin directly. | ✓ (refined) |

**User's choice:** Initially "Footer link", then refined to "Hidden (URL only)" in the access control discussion.
**Notes:** The final decision is no visible link from the dashboard — access by knowing the URL. This supersedes the initial "Footer link" choice.

---

## Access control

### Q1: Should the admin panel require authentication?

| Option | Description | Selected |
|--------|-------------|----------|
| No auth (LAN trust) | LAN-only trust like the rest of the dashboard. | ✓ |
| Admin password (env token) | Shared admin password stored in env. Prompted on first visit. | |
| Reuse nova_api_token | If set, /admin requires it; if not set, open. | |

**User's choice:** No auth (LAN trust)
**Notes:** 2-person household on a private network; network access is the security boundary.

### Q2: If no auth, should the admin page be discoverable from the dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Footer link (as decided) | Visible but not prominent. | |
| Hidden (URL only) | No link at all — must know the URL. Mild obscurity. | ✓ |
| Conditional link (admin user only) | Only visible to 'admin' users. | |

**User's choice:** Hidden (URL only)
**Notes:** Refines the earlier navigation decision — no link from the dashboard at all. Access by typing /admin directly.

---

## the agent's Discretion

- Exact layout of the admin page (card grid, list, sections)
- SSE interval for health checks (30s-60s range)
- Whether to create a new /admin/stream SSE endpoint or extend /dashboard/stream
- Backend health-check endpoint structure (single /admin/status or per-service)
- Error/loading states for unreachable services
- Whether to show a "Back to Dashboard" link on the admin page

## Deferred Ideas

- Audit log viewer with filtering — future phase
- Config viewer (read-only display of env settings) — future phase
- Memory management (view/clear long-term memories) — future phase
- Write actions (restart Ollama, run migrations, clear cache) — future phase
- Admin authentication / multi-user admin roles — not needed for 2-person LAN household
- Webhook health diagnostics (last received timestamp per channel) — future enhancement
