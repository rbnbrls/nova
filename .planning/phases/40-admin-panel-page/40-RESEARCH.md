# Phase 40: admin panel page - Research

**Researched:** 2026-07-13
**Domain:** FastAPI SSE endpoint + vanilla HTML/CSS/JS admin status board (read-only, LAN-only, no auth)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Panel Scope
- **D-01:** System status + channel link status only. No audit log viewer, no config viewer, no memory management — those are out of scope for Phase 40.
- **D-02:** Health indicators with key details per service: Ollama (model name qwen3:14b, ready/not), Postgres (connected, table counts), CalDAV (reachable, URL), Home Assistant (reachable, URL), email IMAP (connected, configured address). Ping-style checks with contextual details.
- **D-03:** Channel link status: WhatsApp and Telegram linked/unlinked per user (Ruben, Méral). Reuse existing data from the preferences/linking endpoints — just surface it on the admin page.
- **D-04:** No write actions — read-only monitoring. No restart, no config editing, no memory clearing. This is a status board, not a control panel.

#### Page Architecture
- **D-05:** Separate HTML page at `/static/admin.html` with a `/admin` route redirect (mirrors the `/dashboard` → `/static/index.html` pattern in `main.py:281-283`).
- **D-06:** Shared `style.css` (reuse glass-panel, button, badge, grid styles), separate `admin.js` (admin-specific logic only — do not add to `app.js`).
- **D-07:** No visible link from the household dashboard. The admin page is accessed by typing `/admin` directly. No footer link, no header link — intentional obscurity on top of LAN trust.

#### Access Control
- **D-08:** No authentication — LAN-only trust, same as the existing dashboard. The household is 2 people on a private network; network access is the security boundary.
- **D-09:** No discoverability — the admin URL is not advertised on the dashboard. Must know `/admin` to access.

#### Status Refresh
- **D-10:** SSE real-time push for status updates. Extend the existing `/dashboard/stream` SSE pattern or create a new `/admin/stream` endpoint that pushes health check results on an interval.

### the agent's Discretion
- Exact layout of the admin page (card grid, list, sections) — keep the glass-panel aesthetic consistent with the dashboard.
- SSE interval for health checks (30s-60s range is reasonable; balance freshness vs. load).
- Whether to create a new `/admin/stream` SSE endpoint or extend `/dashboard/stream` with admin events.
- How to structure the backend health-check endpoint (single `/admin/status` that checks all services, or individual per-service endpoints).
- Error/loading states for services that are unreachable.
- Whether to show a "Back to Dashboard" link on the admin page (recommended for usability, but not a hard requirement).

### Deferred Ideas (OUT OF SCOPE)
- Audit log viewer with filtering — belongs in a future phase (the `/dashboard/audit` endpoint and activity feed already exist on the main dashboard).
- Config viewer (read-only display of all env settings) — future phase.
- Memory management (view/clear long-term memories per user) — future phase; adds write actions.
- Write actions (restart Ollama, run migrations, clear cache) — future phase; significantly increases backend complexity.
- Admin authentication / multi-user admin roles — not needed for a 2-person LAN household.
- Webhook health diagnostics (last received timestamp per channel) — future enhancement.
</user_constraints>

<phase_requirements>
## Phase Requirements

Phase 40 has no formal requirement IDs in `REQUIREMENTS.md` (all v3.0 requirements are already complete). The phase derives its requirements from the CONTEXT.md decisions and the UI-SPEC.md design contract. Planner should treat D-01..D-10 + UI-SPEC layout contract as the requirement set.

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | System status + channel link status only | Scope boundary — see Architecture Patterns |
| D-02 | Health indicators with key details per service (Ollama, Postgres, CalDAV, HA, email IMAP) | Don't Hand-Roll table — reuse `llm.is_ready()`, `db.get_pool()`, `_get_calendar()`, `_ha_get()`, `_get_imap_connection()` |
| D-03 | Channel link status per user (Ruben, Méral) | Reuse `/api/preferences` query pattern (main.py:684-713) |
| D-04 | Read-only — no write actions | No POST/PUT/DELETE endpoints in this phase |
| D-05 | `/admin` redirect → `/static/admin.html` | Mirror main.py:281-283 `dashboard_redirect()` |
| D-06 | Shared `style.css`, separate `admin.js` | See Architecture Patterns — reusing design tokens |
| D-07 | No discoverability — `index.html` MUST NOT gain an admin link | Verification step: grep `index.html` diff for `/admin` |
| D-08 | No auth — LAN trust | See Security Domain (ASVS L1) |
| D-09 | No discoverability | Same verification as D-07 |
| D-10 | SSE push for status updates | See Code Examples — `StreamingResponse` SSE pattern |
| UI-SPEC | Visual/interaction contract | See Architectural Responsibility Map + Code Examples |
</phase_requirements>

## Summary

Phase 40 is a small, tightly-constrained, greenfield addition: a read-only admin status board at `/admin` that mirrors the household dashboard's glass-panel aesthetic and reuses its SSE pattern. The phase touches **4 new files** (`static/admin.html`, `static/admin.js`, plus minor additions to `static/style.css` and `services/nova-core/app/main.py`) and introduces **zero new packages** — every library the implementation needs (FastAPI, httpx, asyncpg, caldav, aioimaplib) is already in `requirements.txt` and already used by the existing `/health`, `/dashboard/stream`, `/dashboard/tasks`, `/dashboard/events`, `/api/preferences` endpoints.

The dominant research finding is that the codebase already contains a fully-working blueprint for everything this phase needs: the `/dashboard/stream` SSE generator (`main.py:286-307`), the `/dashboard` redirect (`main.py:281-283`), the `/api/preferences` query (`main.py:684-713`), the Ollama `is_ready()` health check (`llm.py:85-92`), the asyncpg `get_pool()` (`db.py:15-19`), the CalDAV `_get_calendar()` (`tools/calendar.py:20-26`), the HA REST helper (`tools/home_assistant.py:38-55`), and the IMAP `_get_imap_connection()` (`tools/email.py:27-40`). The new `/admin/stream` endpoint is structurally a clone of `/dashboard/stream` with a different payload and a longer sleep interval (45s per UI-SPEC vs. 15s for the dashboard).

**Primary recommendation:** Build `/admin/stream` as a single SSE generator that runs `asyncio.gather(*[asyncio.wait_for(check, timeout=N) for check in checks], return_exceptions=True)` on a 45-second interval, returning `{services: {ollama, postgres, caldav, ha, email}, channels: {Ruben: {whatsapp, telegram}, Méral: {whatsapp, telegram}}}`. Clone `/dashboard` redirect → `/admin`. Clone `index.html` → `admin.html` with the admin-specific grid from UI-SPEC §Layout. Clone `app.js` SSE-handling subset → `admin.js`. Do NOT touch `index.html` (D-07 verification gate).

**Secondary recommendation:** Per the UI-SPEC layout contract, the admin page has two stacked cards spanning the 2-column grid: top = `System Status` (5-cell inner grid: Ollama, Postgres, CalDAV, HA, Email), bottom = `Channel Status` (per-user tab selector `Ruben`/`Méral` + WhatsApp/Telegram cells). Use named SSE events (`event: status\ndata: {...}\n\n`) so `admin.js` can use `addEventListener('status', cb)` — this is more idiomatic than the existing dashboard's unnamed `onmessage` pattern and cleanly separates event types if the admin stream grows.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| System health checks (Ollama, Postgres, CalDAV, HA, IMAP) | API / Backend (nova-core) | — | All 5 backends are reachable only from nova-core's network namespace (per `docker-compose.yml`); browser cannot reach them. Health checks must run server-side. |
| Channel link status (WhatsApp/Telegram per user) | API / Backend (nova-core) | Database / Storage | Reuses the same `user_preferences` + `channel_identities` tables already queried by `/api/preferences`. |
| SSE transport (push status to admin page) | API / Backend (nova-core) | — | `StreamingResponse` with `text/event-stream` is a FastAPI/server responsibility; existing `/dashboard/stream` is the template. |
| Admin page rendering (status cards, indicators, tabs) | Browser / Client | — | Vanilla JS in `admin.js` renders the JSON payload into the DOM; no SSR. |
| Static asset serving (`admin.html`, `admin.js`) | CDN / Static | — | Existing `StaticFiles` mount at `/static` (`main.py:976-977`) serves both files automatically — no new mount needed. |
| Page routing (`/admin` → `/static/admin.html`) | API / Backend (nova-core) | — | FastAPI `RedirectResponse` mirroring `dashboard_redirect()` (`main.py:281-283`). |
| Authentication / access control | Network (LAN) | — | D-08 locks: no app-level auth. The Proxmox VM + LAN is the security boundary. Caddy `nova.local` route is LAN-only by design. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.115.6 | Web framework hosting `/admin` redirect + `/admin/stream` SSE endpoint | Already used by every nova-core endpoint; pinned in `services/nova-core/requirements.txt` [VERIFIED: requirements.txt] |
| Starlette `StreamingResponse` | (bundled with FastAPI) | SSE response class — async generator yields `data: {...}\n\n` chunks | Already used by `/dashboard/stream` (`main.py:307`); FastAPI re-exports from starlette.responses [CITED: fastapi.tiangolo.com/advanced/custom-response/#streamingresponse] |
| httpx | 0.28.1 | Async HTTP client for Ollama `/api/version`, HA `/api/` health pings | Already used by `llm.is_ready()` and `tools/home_assistant._ha_get()` [VERIFIED: requirements.txt, llm.py:88] |
| asyncpg | 0.30.0 | Postgres pool for `SELECT 1` + table-count health query | Already used by every dashboard endpoint via `db.get_pool()` [VERIFIED: requirements.txt, db.py:18] |
| caldav | 1.3.9 | CalDAV client for "is the calendar URL reachable" check | Already used by `_get_calendar()` (`tools/calendar.py:21`); the admin check can call `client.principal()` in a `try/except` [VERIFIED: requirements.txt] |
| aioimaplib | 2.0.1 | Async IMAP client for "is IMAP login working" check | Already used by `_get_imap_connection()` (`tools/email.py:27-40`); admin check can call `wait_hello_from_server()` + `login()` and catch exceptions [VERIFIED: requirements.txt] |
| EventSource (browser API) | n/a | Client-side SSE consumer in `admin.js` | Built into all modern browsers; same API used by existing `app.js:13` [CITED: developer.mozilla.org/en-US/docs/Web/API/EventSource] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | Python 3.12 | `asyncio.gather(return_exceptions=True)` + `asyncio.wait_for(timeout=N)` for concurrent health checks with per-check timeout | ALWAYS — 5 backends × 5s timeout running serially could block SSE generator up to 25s; concurrent gather caps total at ~5s [CITED: docs.python.org/3.12/library/asyncio-task.html] |
| zoneinfo (stdlib) | Python 3.12 | Timezone handling if timestamps are emitted | Already imported in `main.py:21`; the admin SSE payload does not require timestamps but a `checked_at` field is useful |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.gather(return_exceptions=True)` | `asyncio.TaskGroup` (Python 3.11+) | TaskGroup cancels remaining tasks on first failure — wrong for health checks (we want ALL results even if one fails). gather-with-return_exceptions is the correct primitive. [CITED: docs.python.org/3.12/library/asyncio-task.html] |
| `asyncio.wait_for(timeout=5)` | `asyncio.timeout(5)` context manager (3.11+) | Both work; `wait_for` is simpler for wrapping a single coroutine. The existing codebase style uses neither — but the pattern is straightforward. |
| New `/admin/stream` SSE endpoint | Extend `/dashboard/stream` with admin events | UI-SPEC §SSE/Refresh Interaction locks the new-endpoint approach. Keeps dashboard stream lean (15s, 3 endpoints) and admin stream slow (45s, 1 endpoint). Different cadence → different endpoint. |
| Single `/admin/status` JSON endpoint + polling | SSE push | D-10 locks SSE; polling was rejected in the discussion (DISCUSSION-LOG Q4). |

**Installation:**

```bash
# No packages to install — all dependencies already in:
# services/nova-core/requirements.txt
```

**Version verification:** All 7 pinned packages above were verified present in `services/nova-core/requirements.txt` during this research session (2026-07-13). No `npm view` / `pip index versions` calls needed — no new packages introduced.

## Package Legitimacy Audit

> Phase 40 introduces **zero new packages**. Every library used is already pinned in `services/nova-core/requirements.txt` and already imported by existing endpoints. The Package Legitimacy Gate protocol was completed by reading `requirements.txt` (no registry lookups required for already-installed packages).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| fastapi | PyPI | established | high | github.com/fastapi/fastapi | OK (existing) | Already installed — no action |
| httpx | PyPI | established | high | github.com/encode/httpx | OK (existing) | Already installed — no action |
| asyncpg | PyPI | established | high | github.com/MagicStack/asyncpg | OK (existing) | Already installed — no action |
| caldav | PyPI | established | medium | github.com/python-caldav/caldav | OK (existing) | Already installed — no action |
| aioimaplib | PyPI | established | medium | github.com/bamthomas/aioimaplib | OK (existing) | Already installed — no action |
| aiosmtplib | PyPI | established | medium | github.com/cole/aiosmtplib | OK (existing) | Already installed — no action (not directly needed by admin, but listed for completeness) |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*No new packages discovered via WebSearch or training data — all package references in this research were verified against the existing `requirements.txt` on disk. No `checkpoint:human-verify` tasks needed for installs.*

## Architecture Patterns

### System Architecture Diagram

```text
[Browser]
   │
   │  (1) GET /admin                    ┌─────────────────────────────────────────────┐
   ├──────────────────────────────────► │ nova-core / main.py                          │
   │                                    │   dashboard_redirect() pattern — D-05         │
   │  (2) 307 → /static/admin.html      │   return RedirectResponse("/static/admin.html")
   │ ◄──────────────────────────────────┤                                             │
   │                                    └─────────────────────────────────────────────┘
   │
   │  (3) GET /static/admin.html        ┌─────────────────────────────────────────────┐
   ├──────────────────────────────────► │ StaticFiles mount (main.py:976-977)          │
   │  + GET /static/admin.js            │   Serves files from services/nova-core/static/
   │  + GET /static/style.css           │   (admin.html, admin.js auto-served)          │
   │ ◄──────────────────────────────────┤                                             │
   │                                    └─────────────────────────────────────────────┘
   │
   │  (4) EventSource('/admin/stream')  ┌─────────────────────────────────────────────┐
   ├──────────────────────────────────► │ nova-core / main.py                          │
   │   long-lived text/event-stream     │   admin_stream() → StreamingResponse          │
   │                                    │   event_generator():                          │
   │                                    │     while True:                                │
   │                                    │       payload = await _collect_status()       │
   │                                    │       yield f"event: status\ndata: {json}\n\n" │
   │                                    │       await asyncio.sleep(45)                  │
   │                                    │                                               │
   │                                    │   _collect_status():                           │
   │                                    │     results = await asyncio.gather(            │
   │                                    │       *[asyncio.wait_for(check, timeout=5)     │
   │                                    │         for check in [                        │
   │                                    │           _check_ollama(),                    │
   │                                    │           _check_postgres(),                 │
   │                                    │           _check_caldav(),                    │
   │                                    │           _check_ha(),                         │
   │                                    │           _check_imap(),                       │
   │                                    │       ]],                                      │
   │                                    │       return_exceptions=True,                  │
   │                                    │     )                                          │
   │                                    │     channels = await _collect_channels()       │
   │                                    │     return {services, channels}                │
   │                                    │                                               │
   │                                    │   _check_*():  reuse llm.is_ready / db.get_pool │
   │                                    │                / _get_calendar / _ha_get /     │
   │                                    │                _get_imap_connection            │
   │                                    │                                               │
   │  (5) event: status data: {...}     │   (every 45s)                                 │
   │ ◄──────────────────────────────────┤                                             │
   │                                    └─────────────────────────────────────────────┘
   │
   ▼
[admin.js renders payload into DOM cells — green/red pulse-dot + detail line]
```

The reader can trace the primary use case from input to output: browser types `/admin` → redirect to static HTML → static assets served → `admin.js` opens `EventSource('/admin/stream')` → backend generator runs 5 concurrent health checks every 45s → JSON payload pushed → JS re-renders DOM cells with green/red indicators + detail lines.

### Recommended Project Structure

```text
services/nova-core/
├── app/
│   └── main.py              # ADD: GET /admin redirect, GET /admin/stream SSE,
│                            #      helpers: _check_ollama, _check_postgres,
│                            #      _check_caldav, _check_ha, _check_imap,
│                            #      _collect_status, _collect_channels
├── static/
│   ├── admin.html           # NEW: admin page (mirror of index.html structure)
│   ├── admin.js             # NEW: SSE consumer + DOM renderer
│   ├── style.css            # ADD: small admin-specific block (service-cell grid,
│   │                        #      channel-status-cell pattern)
│   ├── app.js               # UNCHANGED (D-07 verification gate)
│   └── index.html           # UNCHANGED (D-07 verification gate)
└── tests/
    └── test_admin.py        # NEW: covers /admin redirect, /admin/stream SSE,
                             #      _collect_status with mocked checks
```

### Pattern 1: Clone the `/dashboard` redirect for `/admin`

**What:** Add a one-line FastAPI route that returns `RedirectResponse(url="/static/admin.html")`. StaticFiles mount already serves `/static/*`, so no new mount needed.

**When to use:** For any separate static page that should have a clean URL alias (per D-05).

**Example:**

```python
# Source: services/nova-core/app/main.py:281-283 (existing dashboard pattern to clone)
@app.get("/admin")
async def admin_redirect():
    return RedirectResponse(url="/static/admin.html")
```

### Pattern 2: SSE generator with named events + concurrent health checks

**What:** Clone the `/dashboard/stream` generator shape (`main.py:286-307`) but emit a named `event: status` so `admin.js` can use `addEventListener('status', cb)`. Run health checks concurrently with `asyncio.gather(return_exceptions=True)` so a slow/dead backend does not block the others.

**When to use:** Any SSE endpoint that aggregates multiple independent data sources on a fixed interval.

**Example:**

```python
# Source: pattern adapted from main.py:286-307 (existing) + asyncio docs
# [CITED: docs.python.org/3.12/library/asyncio-task.html#asyncio.gather]
@app.get("/admin/stream")
async def admin_stream():
    import asyncio
    import json

    async def event_generator():
        while True:
            try:
                payload = await _collect_admin_status()
                # Named event so admin.js uses addEventListener('status', cb)
                yield f"event: status\ndata: {json.dumps(payload)}\n\n"
            except Exception as e:
                # Log and continue — never crash the SSE generator
                log.warning("admin SSE generator error: %s", e)
            await asyncio.sleep(45)  # 45s per UI-SPEC §SSE/Refresh

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _collect_admin_status() -> dict:
    """Run all 5 health checks concurrently with per-check 5s timeout."""
    services_results = await asyncio.gather(
        asyncio.wait_for(_check_ollama(), timeout=5),
        asyncio.wait_for(_check_postgres(), timeout=5),
        asyncio.wait_for(_check_caldav(), timeout=5),
        asyncio.wait_for(_check_ha(), timeout=5),
        asyncio.wait_for(_check_imap(), timeout=5),
        return_exceptions=True,  # one failure must not abort the others
    )
    services = {
        "ollama":   _format_service("ollama",   services_results[0]),
        "postgres": _format_service("postgres", services_results[1]),
        "caldav":   _format_service("caldav",   services_results[2]),
        "ha":       _format_service("ha",       services_results[3]),
        "email":    _format_service("email",    services_results[4]),
    }
    channels = await _collect_channel_status()
    return {"services": services, "channels": channels}
```

### Pattern 3: Reuse existing health-check helpers — do not reimplement

**What:** Each `_check_*` helper wraps an existing function in `try/except` and returns `{status: "ok"|"down", detail: str, host: str}`. The host is derived from `settings` (host:port only — never the full URL with credentials, per the untrusted-input-boundary rule).

**When to use:** For every service check. The point is to reuse, not reinvent.

**Example:**

```python
# Source: services/nova-core/app/llm.py:85-92 (existing is_ready to reuse)
async def _check_ollama() -> dict:
    try:
        ready = await llm.is_ready()  # existing helper — already swallows httpx.HTTPError
        return {
            "status": "ok" if ready else "down",
            "detail": f"Model: {settings.nova_model}" if ready else "Not ready",
            "host": _host_only(settings.ollama_base_url),
        }
    except Exception as e:
        return {"status": "down", "detail": f"Ollama error: {e}", "host": _host_only(settings.ollama_base_url)}


async def _check_postgres() -> dict:
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        return {"status": "ok", "detail": f"{table_count} tables reachable", "host": f"{settings.postgres_host}:{settings.postgres_port}"}
    except Exception as e:
        return {"status": "down", "detail": f"Cannot acquire pool: {e}", "host": f"{settings.postgres_host}:{settings.postgres_port}"}


def _host_only(url: str) -> str:
    """Strip scheme, credentials, path — return host:port only (per untrusted-input-boundary)."""
    from urllib.parse import urlparse
    p = urlparse(url)
    return p.netloc or url
```

### Pattern 4: Channel status — reuse the `/api/preferences` query

**What:** The admin page surfaces WhatsApp/Telegram link status per user. The exact query already exists at `main.py:684-713` (`get_preferences`). The admin backend should run a similar query (or call the same logic) and shape the result as `{Ruben: {whatsapp: {linked: bool, identifier: str}, telegram: {linked: bool, identifier: str}}, Méral: {...}}`.

**When to use:** For the channel status card — D-03 explicitly says "reuse existing data."

**Example:**

```python
# Source: query adapted from services/nova-core/app/main.py:684-713 (existing)
async def _collect_channel_status() -> dict:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.name,
                   up.whatsapp_number,
                   ci_t.channel_id AS telegram_chat_id,
                   up.channels_enabled
            FROM users u
            LEFT JOIN user_preferences up ON u.id = up.user_id
            LEFT JOIN channel_identities ci_t
                ON ci_t.user_id = u.id AND ci_t.channel = 'telegram'
            WHERE u.name IN ('Ruben', 'Meral')
            """
        )
    channels = {}
    for r in rows:
        wa_linked = bool(r["whatsapp_number"])
        tg_enabled = bool(r["channels_enabled"] and "telegram" in r["channels_enabled"])
        channels[r["name"]] = {
            "whatsapp": {
                "linked": wa_linked,
                "identifier": _mask_identifier(r["whatsapp_number"] or ""),
            },
            "telegram": {
                "linked": tg_enabled or bool(r["telegram_chat_id"]),
                "identifier": "Telegram" if r["telegram_chat_id"] else "",
            },
        }
    return channels


def _mask_identifier(number: str) -> str:
    """Mask channel identifiers per UI-SPEC §Copywriting — privacy scope."""
    if not number:
        return ""
    # e.g. "+31 6 12 … 8" — first 6 + last 1, middle masked
    n = number.lstrip("+")
    if len(n) <= 7:
        return f"+{n}"
    return f"+{n[:6]} … {n[-1]}"
```

### Anti-Patterns to Avoid

- **Do NOT extend `/dashboard/stream`** with admin events. UI-SPEC §SSE/Refresh Interaction locks the decision to a new endpoint — the dashboard stream is 15s/3-data-sources, the admin stream is 45s/health-only. Different cadence → different endpoint.
- **Do NOT add an `/admin` link to `index.html`**. D-07/D-09 lock no discoverability. The verification step MUST include a `grep` confirming `index.html` was not modified to add `/admin` references.
- **Do NOT expose full config URLs in the DOM.** Per `references/untrusted-input-boundary.md` and UI-SPEC §Copywriting: only `host:port` is rendered — never credentials, tokens, passwords, or full URLs. The `_host_only()` helper enforces this.
- **Do NOT add admin logic to `app.js`.** D-06 locks separate `admin.js`. The dashboard's `app.js` is already ~990 lines — admin code must not bloat it.
- **Do NOT run health checks serially.** 5 services × 5s timeout = 25s if serial; concurrent `asyncio.gather` caps total at ~5s. Serial checks would push the SSE interval effectively to 70s (45s sleep + 25s checks) — unacceptable.
- **Do NOT add the admin endpoint to `main.py` in a place that triggers import cycles.** New helpers reuse `llm`, `db`, `tools.calendar`, `tools.home_assistant`, `tools.email` — all already imported at the top of `main.py` or importable on demand. Pattern: import tool helpers locally inside `_check_*` functions if needed (matches the existing `from .tools.calendar import _get_calendar` style at `main.py:36`).
- **Do NOT add a `pulse` animation to red (down) status dots.** UI-SPEC §Copywriting locks: "pulse is reserved for healthy state only." The red dot is a static circle.
- **Do NOT introduce a third font weight or fifth type size.** UI-SPEC §Typography locks the existing 4-size, 2-weight system. Service names reuse Body 15px / weight 600.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Ollama health check | New httpx call to `/api/version` | `llm.is_ready()` (`llm.py:85-92`) | Already exists, already swallows `httpx.HTTPError`, already used by `/health` endpoint |
| Postgres connectivity check | New pool acquisition + query | `db.get_pool()` + `conn.execute("SELECT 1")` (`db.py:15-19`) | Already used by every dashboard endpoint |
| Postgres table count | New metadata query | `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'` | Standard catalog query; asyncpg returns it as a scalar via `fetchval` |
| CalDAV reachability | New CalDAV client setup | `_get_calendar()` from `tools/calendar.py:20-26` (wrap in try/except) | Already wired to `settings.caldav_url`; raises on unreachable |
| HA reachability | New httpx call to HA `/api/` | `tools/home_assistant._ha_get("/")` (`tools/home_assistant.py:38-55`) | Already returns `{"error": ...}` on failure — distinguish reachable vs not by inspecting the dict |
| IMAP login check | New IMAP connection | `tools/email._get_imap_connection()` (`tools/email.py:27-40`) (wrap in try/except) | Already handles `wait_hello_from_server()` + `login()`; returns None if `nova_imap_host` unset |
| Channel link status query | New SQL query from scratch | Reuse the `get_preferences` query at `main.py:684-713` (extend with `channel_identities` join) | Same `user_preferences` + `channel_identities` tables |
| SSE generator | New async generator pattern | Clone `/dashboard/stream` shape (`main.py:286-307`) + add `event: status` line | Already proven; FastAPI `StreamingResponse` with `text/event-stream` |
| Admin page HTML/CSS structure | New design language | Clone `index.html` header + dashboard-container + glass-panel pattern; reuse `style.css` tokens | D-06 locks shared aesthetic |
| Identifier masking | Custom masker | Match the existing `+{n}` pattern from `app.js:233` (`'+' + userPrefs.whatsapp_number`) | Consistent with existing UI |

**Key insight:** Phase 40 is a "wiring" phase, not an "inventing" phase. Every primitive the implementation needs already exists in the codebase. The new code's job is to (a) call the existing helpers concurrently, (b) shape the results into one JSON payload, (c) push it via SSE, (d) render it into a cloned glass-panel layout. The single genuine "new logic" is the `asyncio.gather(return_exceptions=True)` fan-out — and that is a 3-line standard-library pattern.

## Common Pitfalls

### Pitfall 1: Serial health checks blocking the SSE generator

**What goes wrong:** The implementer writes 5 sequential `await check_x()` calls. If CalDAV is down and takes 5s to timeout, the SSE generator takes 5s + 5s + 5s + 5s + 5s = 25s per cycle, effectively pushing the interval to 70s (45s sleep + 25s checks).
**Why it happens:** Sequential code reads more naturally than `asyncio.gather(*[...], return_exceptions=True)`.
**How to avoid:** Use the concurrent gather pattern from Pattern 2 above. Cap each check with `asyncio.wait_for(check, timeout=5)` so a hung backend cannot exceed 5s.
**Warning signs:** SSE events arriving more than 50s apart (vs. the 45s target) in the browser's Network tab.

### Pitfall 2: Forgetting `await asyncio.sleep()` inside the SSE generator

**What goes wrong:** The generator yields events in a tight loop without `await asyncio.sleep(45)`, causing the endpoint to flood the client with events as fast as it can compute them, or — more dangerously — without any `await` at all the generator never yields control to the event loop and cannot be cancelled when the client disconnects.
**Why it happens:** FastAPI's docs explicitly warn: "An async task can only be cancelled when it reaches an await. If there is no await, the generator can not be cancelled properly and may keep running even after cancellation is requested." [CITED: fastapi.tiangolo.com/advanced/custom-response/#streamingresponse]
**How to avoid:** Always include `await asyncio.sleep(45)` at the end of the `while True` loop. The existing `/dashboard/stream` (`main.py:305`) does exactly this with `await asyncio.sleep(15)`.
**Warning signs:** Server log shows the SSE generator still running after the browser tab is closed; CPU usage stays elevated.

### Pitfall 3: Rendering credentials/tokens to the DOM

**What goes wrong:** The admin page shows `settings.nova_ha_url` (which contains no secret) but a future maintainer copies the pattern and shows `settings.nova_imap_pass` or `settings.telegram_bot_token`.
**Why it happens:** The admin page is for "system status with key details" — the temptation is to show "everything" for debugging.
**How to avoid:** Use the `_host_only()` helper (Pattern 3) for every URL field. Never render raw `settings.*_token`, `settings.*_pass`, `settings.*_secret`, `settings.*_password` values. The UI-SPEC §Copywriting locks this: "{host} MUST be derived from config (host + port only, never the full URL with credentials)."
**Warning signs:** A `{{ token }}` or `{{ password }}` template variable; any field that uses `settings.nova_*` directly without filtering through `_host_only()` or equivalent.

### Pitfall 4: Breaking D-07 (no discoverability) by editing `index.html`

**What goes wrong:** The implementer helpfully adds a small "Admin" footer link or a hidden `<a href="/admin">` to the dashboard.
**Why it happens:** Natural UX instinct — "users need a way to navigate."
**How to avoid:** The user's decision is explicit (D-07, D-09): "No visible link from the household dashboard. The admin page is accessed by typing /admin directly. No footer link, no header link — intentional obscurity on top of LAN trust." The verification step MUST include a `git diff services/nova-core/static/index.html` showing zero changes to `index.html`. A `grep -n "/admin" services/nova-core/static/index.html` should return nothing.
**Warning signs:** Any change to `index.html` in the PR diff.

### Pitfall 5: Letting `EventSource.onerror` show a modal

**What goes wrong:** When the SSE connection drops (server restart, network blip), the admin page throws a modal dialog or alert.
**Why it happens:** Developers default to "user must know about every error."
**How to avoid:** UI-SPEC §SSE/Refresh Interaction locks: "On `EventSource` `onerror`, show the page-level error banner (`.chat-error` styling) `Admin stream disconnected. Retrying…` — browser auto-reconnects; do NOT throw a modal." The browser's `EventSource` automatically reconnects on error — surface the state with a banner, not a modal. [CITED: developer.mozilla.org/en-US/docs/Web/API/EventSource]
**Warning signs:** Any `alert()` or `confirm()` call in `admin.js`; any modal `hidden` class toggling in the `onerror` handler.

### Pitfall 6: Re-animating unchanged cells on every SSE event

**What goes wrong:** On each 45s event, `admin.js` does `container.innerHTML = newHtml`, causing every cell to flash/re-animate even if the status did not change.
**Why it happens:** Simplest implementation is full innerHTML replacement.
**How to avoid:** UI-SPEC §SSE/Refresh Interaction locks: "Unchanged cells MUST keep their existing DOM (no flash/re-animation) — only changed cells swap content + animate via existing `@keyframes fadeIn`." Compare previous payload to new payload per cell; only update the cell if its status/detail changed. The `data-status` attribute pattern (e.g. `data-status="ok"`) makes diffing trivial — only re-render if `newCell.status !== oldCell.dataset.status`.
**Warning signs:** All cells visibly flash every 45s in the browser; CSS `fadeIn` animation runs on every event.

## Code Examples

Verified patterns from the codebase and official docs:

### Existing `/dashboard/stream` SSE generator (the template to clone)

```python
# Source: services/nova-core/app/main.py:286-307 (verbatim — existing implementation)
@app.get("/dashboard/stream")
async def dashboard_stream():
    import asyncio
    import json

    async def event_generator():
        while True:
            try:
                tasks_data = await dashboard_tasks()
                events_data = await dashboard_events()
                audit_data = await dashboard_audit(limit=50)
                payload = {
                    "tasks": tasks_data["tasks"],
                    "events": events_data["events"],
                    "audit": audit_data["audit"],
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                print(f"[ERROR] SSE generator error: {e}")
            await asyncio.sleep(15)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

> **Adaptation for `/admin/stream`:** (1) Wrap each check in `asyncio.wait_for(timeout=5)` and run them via `asyncio.gather(return_exceptions=True)` instead of sequential `await`. (2) Add `event: status\n` before the `data:` line to use named events. (3) Change sleep to 45s. (4) Use `log.warning(...)` instead of `print(...)` to match the `log = logging.getLogger("nova-core")` style at `main.py:42`.

### Existing `/dashboard` redirect (the template to clone)

```python
# Source: services/nova-core/app/main.py:281-283 (verbatim)
@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/static/index.html")
```

### Existing `EventSource` consumer pattern (the template to clone)

```javascript
// Source: services/nova-core/static/app.js:13-32 (verbatim — existing dashboard pattern)
const eventSource = new EventSource('/dashboard/stream');

eventSource.onmessage = function(event) {
    try {
        const data = JSON.parse(event.data);
        updateTasks(data.tasks);
        updateEvents(data.events);
        updateAudit(data.audit);
        document.querySelector('.status-text').textContent = 'Live Connected';
        document.querySelector('.pulse-dot').style.backgroundColor = '#10b981';
    } catch (e) {
        console.error('Failed to parse SSE event:', e);
    }
};

eventSource.onerror = function(err) {
    console.error('SSE connection lost, reconnecting...', err);
    document.querySelector('.status-text').textContent = 'Disconnected (Reconnecting...)';
    document.querySelector('.pulse-dot').style.backgroundColor = '#ef4444';
};
```

> **Adaptation for `admin.js`:** Switch from `onmessage` to `addEventListener('status', cb)` because the admin endpoint emits named events (`event: status\ndata: {...}\n\n`). The `onerror` handler sets the page-level `.chat-error` banner text to `Admin stream disconnected. Retrying…` instead of toggling the dot color (per UI-SPEC §SSE/Refresh Interaction). The browser auto-reconnects — do NOT call `eventSource.close()` in the error handler.

### Existing `/api/preferences` query (the SQL to extend)

```python
# Source: services/nova-core/app/main.py:686-713 (existing — admin extends with channel_identities join)
pool = await db.get_pool()
async with pool.acquire() as conn:
    rows = await conn.fetch(
        """
        SELECT u.name, up.whatsapp_number, up.dnd_enabled, up.dnd_start, up.dnd_end,
               up.morning_briefing_enabled, up.morning_briefing_time,
               up.weekly_briefing_enabled, up.weekly_briefing_day, up.weekly_briefing_time,
               up.channels_enabled
        FROM users u
        LEFT JOIN user_preferences up ON u.id = up.user_id
        WHERE u.name IN ('Ruben', 'Meral')
        """
    )
```

> **Adaptation for `_collect_channel_status`:** Add a `LEFT JOIN channel_identities ci_t ON ci_t.user_id = u.id AND ci_t.channel = 'telegram'` to fetch the Telegram chat_id alongside the WhatsApp number, then shape into the per-user per-channel dict (Pattern 4 above).

### Existing test pattern (the test file to clone)

```python
# Source: services/nova-core/tests/test_dashboard.py:1-16 (verbatim — existing test infrastructure)
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_redirect(client):
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/index.html"
```

> **Adaptation for `test_admin.py`:** Same structure. `test_admin_redirect` asserts 307 + `/static/admin.html`. `test_admin_stream_sse` mocks the 5 health checks and reads the first line of the stream (clone `test_dashboard_stream_sse` at `test_dashboard.py:59-99`). `test_admin_html_has_system_status_panel` asserts the static `admin.html` contains the expected section IDs (clone `test_dashboard_html_has_chat_panel` at `test_dashboard.py:128-132`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.wait()` primitive | `asyncio.gather(return_exceptions=True)` for fan-out + `asyncio.wait_for()` for per-task timeout | Python 3.7+ | gather returns results in input order; wait returns `(done, pending)` sets — gather is simpler for fan-out where all results are needed |
| `asyncio.TimeoutError` | `TimeoutError` (builtin) | Python 3.11 | `asyncio.TimeoutError` is deprecated alias for builtin `TimeoutError`; catch `TimeoutError` |
| `asyncio.timeout()` context manager | New alternative to `wait_for` | Python 3.11 | Both work; `wait_for(coro, timeout=N)` is more concise for wrapping a single coroutine |
| Unnamed SSE events (`data: {...}\n\n`) | Named SSE events (`event: status\ndata: {...}\n\n`) | n/a | Named events let the client use `addEventListener('status', cb)` and separate event types cleanly. The existing dashboard uses unnamed; the admin endpoint should use named per UI-SPEC |
| `EventSource` 6-connection-per-browser limit (HTTP/1.1) | HTTP/2 multiplexing (100 streams negotiated) | n/a | Non-issue for Phase 40 — admin page opens only ONE EventSource. The dashboard already opens one. [CITED: developer.mozilla.org/en-US/docs/Web/API/EventSource] |

**Deprecated/outdated:**

- `asyncio.TimeoutError` — use builtin `TimeoutError` (Python 3.11+).
- `print(f"[ERROR] ...")` in production code — use `log.warning(...)` with `%s`-style lazy formatting per `CONVENTIONS.md` §Logging. The existing `/dashboard/stream` uses `print` — admin should use `log.warning` (matches the `log = logging.getLogger("nova-core")` at `main.py:42`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 5 backends (Ollama, Postgres, CalDAV, HA, IMAP) are reachable from nova-core's container network namespace on the URLs in `settings.*` | Architecture / Don't Hand-Roll | LOW — verified by inspecting `docker-compose.yml` service definitions and existing endpoints (`/health` calls Ollama, dashboard endpoints call Postgres, `/dashboard/events` calls CalDAV, `tools/home_assistant.py` calls HA, `tools/email.py` calls IMAP). If a backend is down at runtime, the `try/except` in each `_check_*` returns `status: "down"` — the SSE endpoint does not crash. |
| A2 | `_get_calendar()` (`tools/calendar.py:20-26`) raises on unreachable CalDAV rather than hanging | Don't Hand-Roll | LOW — the `caldav` library uses `requests` under the hood which respects connection timeouts; if it hangs, the `asyncio.wait_for(timeout=5)` wrapper caps the wait at 5s. Worth verifying during execution with a manual test against an unreachable URL. |
| A3 | `_get_imap_connection()` (`tools/email.py:27-40`) returns `None` when `nova_imap_host` is unset, and raises on bad credentials | Don't Hand-Roll | LOW — verified by reading the code: `if not settings.nova_imap_host: return None` (line 32-33); `await imap.login(...)` will raise `aioimaplib.Imap4Error` or similar on bad credentials. The `_check_imap` helper must treat `None` as "not configured" (status: "down", detail: "Not configured") vs. an exception as "down with error". |
| A4 | `tools.home_assistant._ha_get("/")` returns `{"error": "HA not configured..."}` when `NOVA_HA_TOKEN` is unset, and `{"error": "HA connection failed: ..."}` on network failure | Don't Hand-Roll | LOW — verified by reading `tools/home_assistant.py:38-55`. The `_check_ha` helper must inspect the returned dict for an `"error"` key to distinguish reachable from unreachable. |
| A5 | The `channel_identities` table has rows for both WhatsApp and Telegram after Phase 13/21 backfills | Pattern 4 | LOW — verified by reading `db.py:99-133` which seeds both channels during migration. If a row is missing, `LEFT JOIN` returns `NULL`, which the helper interprets as "not linked" (correct behavior). |
| A6 | The admin page will be served via the existing `StaticFiles` mount at `/static` (`main.py:976-977`) without needing a new mount | Architecture | LOW — verified by reading `main.py:976-977`: `app.mount("/static", StaticFiles(directory=static_dir), name="static")`. Any file dropped into `services/nova-core/static/` is auto-served. The existing `app.js` and `index.html` are served this way. |
| A7 | The `audit-panel` CSS pattern (`grid-column: span 2`) at `style.css:706-715` can be reused for the admin's full-width cards | Architecture | LOW — the pattern is generic (just `grid-column: span 2` + media query). The admin page will add a similar block. |

**No [ASSUMED] claims from training data** — all claims above are derived from reading the actual codebase during this research session. The only external knowledge used is the FastAPI/MDN/Python docs which are tagged `[CITED: ...]`.

## Open Questions (RESOLVED)

1. **Should the admin SSE endpoint expose a `/admin/status` JSON snapshot endpoint too?**
   - What we know: D-10 locks SSE. UI-SPEC §SSE/Refresh locks `EventSource('/admin/stream')`.
   - What's unclear: A non-SSE `/admin/status` GET endpoint could be useful for `curl` debugging (e.g. `curl nova.local/admin/status | jq`), but it's not required by any decision.
   - Recommendation: Skip for Phase 40 — out of scope unless D-10 is reinterpreted. If the planner wants it, add as an optional task. The `_collect_admin_status()` helper is reusable for both SSE and a hypothetical snapshot endpoint with no extra work.
   - **RESOLVED: Skipped — out of scope per D-10 (SSE-only). No task adds a snapshot endpoint.**

2. **Should the admin page show a "checked_at" timestamp?**
   - What we know: UI-SPEC §Copywriting does not mention a timestamp. UI-SPEC §SSE/Refresh mentions only `placeholder-loader` text for the initial loading state.
   - What's unclear: A small "Last checked: 14:32:05" line could increase trust in the page.
   - Recommendation: Add a `checked_at` ISO timestamp field to the SSE payload (cheap — `datetime.now(timezone.utc).isoformat()`); `admin.js` can render it in the page header next to the `Live Connection` indicator. If the planner disagrees, it's a one-line removal.
   - **RESOLVED: Rejected — planner chose `{services, channels}`-only payload; no `checked_at` field. UI-SPEC §Copywriting has no checked_at field; the `Live Connection` pulse-dot indicator serves the same trust purpose without a timestamp. Rationale recorded to avoid re-litigation.**

3. **Should the channel status identifier for Telegram show the chat_id?**
   - What we know: UI-SPEC §Copywriting says identifiers are masked per privacy scope, and the WhatsApp mask is `+31 6 12 … 8`.
   - What's unclear: Telegram chat_ids are numeric (e.g. `1234567890`) — masking doesn't make sense the same way.
   - Recommendation: For Telegram, show just `Linked` (no identifier) — the chat_id is not user-meaningful. WhatsApp shows the masked number. This matches the existing settings modal behavior (`app.js:233` shows `+{number}` for WhatsApp, `Linked` / `Not Linked` text for Telegram at `app.js:239`).
   - **RESOLVED: Telegram shows `Linked` only (chat_id is not user-meaningful); WhatsApp shows masked number per UI-SPEC §Copywriting. Plan 01 test asserts empty identifier for Telegram when linked.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | nova-core runtime | ✓ | 3.12-slim (Dockerfile) | — |
| FastAPI | `/admin` + `/admin/stream` routes | ✓ | 0.115.6 (requirements.txt) | — |
| httpx | Ollama + HA health checks | ✓ | 0.28.1 (requirements.txt) | — |
| asyncpg | Postgres health check + channel status query | ✓ | 0.30.0 (requirements.txt) | — |
| caldav | CalDAV reachability check | ✓ | 1.3.9 (requirements.txt) | — |
| aioimaplib | IMAP login check | ✓ | 2.0.1 (requirements.txt) | — |
| pytest + pytest-asyncio | Test suite (`test_admin.py`) | ✓ | (Dockerfile tester stage) | — |
| Browser with `EventSource` | admin.js SSE consumer | ✓ | all modern browsers | — |
| Static file mount at `/static` | serving `admin.html` + `admin.js` | ✓ | existing at `main.py:976-977` | — |

**Missing dependencies with no fallback:** none

**Missing dependencies with fallback:** none

Step 2.6 (Environment Availability Audit) was performed by reading `services/nova-core/requirements.txt` and `services/nova-core/Dockerfile`. Every required dependency is already installed and pinned. No new packages need to be installed. The phase is code/config-only from a dependencies perspective — no external tools, CLIs, or services beyond what the existing nova-core stack already requires.

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` (line 24) — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (installed in Dockerfile tester stage) |
| Config file | none — see `services/nova-core/tests/conftest.py` for path setup + autouse DB mock |
| Quick run command | `cd services/nova-core && python -m pytest tests/test_admin.py -x` |
| Full suite command | `cd services/nova-core && python -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-05 | `GET /admin` returns 307 redirect to `/static/admin.html` | unit | `python -m pytest tests/test_admin.py::test_admin_redirect -x` | ❌ Wave 0 |
| D-06 | `/static/admin.html` is served with 200 | unit | `python -m pytest tests/test_admin.py::test_admin_html_served -x` | ❌ Wave 0 |
| D-07 | `index.html` was NOT modified to add `/admin` link | smoke | `git diff --exit-code services/nova-core/static/index.html && ! grep -q '/admin' services/nova-core/static/index.html` (manual / pre-commit) | ❌ Wave 0 |
| D-08 | `/admin/stream` does NOT require auth (no 401 without token) | unit | `python -m pytest tests/test_admin.py::test_admin_stream_no_auth -x` | ❌ Wave 0 |
| D-10 | `GET /admin/stream` returns `text/event-stream` content-type | unit | `python -m pytest tests/test_admin.py::test_admin_stream_content_type -x` | ❌ Wave 0 |
| D-10 | First SSE event is `event: status` with `data:` containing `{services, channels}` | unit | `python -m pytest tests/test_admin.py::test_admin_stream_payload_shape -x` | ❌ Wave 0 |
| D-02 | `_check_ollama` returns `{status, detail, host}` (mocked `llm.is_ready`) | unit | `python -m pytest tests/test_admin.py::test_check_ollama -x` | ❌ Wave 0 |
| D-02 | `_check_postgres` returns table count when reachable | unit | `python -m pytest tests/test_admin.py::test_check_postgres -x` | ❌ Wave 0 |
| D-02 | `_check_imap` returns `not_configured` when `nova_imap_host` is empty | unit | `python -m pytest tests/test_admin.py::test_check_imap_not_configured -x` | ❌ Wave 0 |
| D-02 | `_collect_admin_status` runs all 5 checks concurrently; one failing check does not abort others | unit | `python -m pytest tests/test_admin.py::test_collect_status_isolation -x` | ❌ Wave 0 |
| D-03 | `_collect_channel_status` returns per-user per-channel linked status | unit | `python -m pytest tests/test_admin.py::test_collect_channel_status -x` | ❌ Wave 0 |
| UI-SPEC | `admin.html` contains `#system-status-panel` + `#channel-status-panel` + per-service cell IDs | smoke | `python -m pytest tests/test_admin.py::test_admin_html_structure -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd services/nova-core && python -m pytest tests/test_admin.py -x`
- **Per wave merge:** `cd services/nova-core && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `services/nova-core/tests/test_admin.py` — covers D-02, D-03, D-05, D-08, D-10, UI-SPEC structure
- [ ] `services/nova-core/tests/test_admin.py` needs shared fixtures (mocked `llm.is_ready`, mocked `db.get_pool`, mocked `_get_calendar`, mocked `_ha_get`, mocked `_get_imap_connection`) — pattern from `tests/test_dashboard.py`
- [ ] Framework install: none — pytest + pytest-asyncio already in Dockerfile tester stage

*(If no gaps: "None — existing test infrastructure covers all phase requirements") — but the existing `tests/test_dashboard.py` is for the dashboard, not admin. New file is required.*

## Security Domain

> `security_enforcement` is `true` in `.planning/config.json` (line 46); `security_asvs_level: 1` (line 47); `security_block_on: "high"` (line 48).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | NO (explicitly disabled by D-08) | D-08 locks: "No authentication — LAN-only trust." Network access is the security boundary (Proxmox VM + LAN + Caddy `nova.local` route). No app-level auth on `/admin` or `/admin/stream`. Documented as accepted risk. |
| V3 Session Management | NO | No sessions — no login, no cookies, no tokens. The admin page is stateless. |
| V4 Access Control | NO (network-level only) | LAN-only trust per D-08. Caddy's `nova.local` route is LAN-resolvable only. No app-level authorization checks. Accepted risk per D-08. |
| V5 Input Validation | YES (output encoding) | All host/detail strings rendered to the DOM must be HTML-escaped. `admin.js` must use the `escapeHtml(text)` helper pattern from `app.js:197-201` (`const div = document.createElement('div'); div.textContent = text; return div.innerHTML`). Never use `innerHTML` with untrusted strings (e.g. exception messages from backends). |
| V6 Cryptography | NO | No crypto operations in this phase. |
| V7 Error Handling | YES | SSE generator must `try/except` every check and yield `status: "down"` rather than crashing (matches existing `/dashboard/stream` `try/except` at `main.py:303-304`). |
| V8 Data Protection | YES (sensitive data not rendered) | Per `references/untrusted-input-boundary.md`: never render `settings.*_token`, `settings.*_pass`, `settings.*_password`, `settings.*_secret` to the DOM. Use `_host_only()` for URL fields. UI-SPEC §Copywriting locks this explicitly. |
| V9 Communications | YES (LAN-only) | Caddy terminates TLS for `nova.local` if configured; HTTP/1.1 SSE on LAN is acceptable. No HSTS requirement for LAN-only host. |
| V13 API & Web Service | YES | `/admin/stream` is a new GET endpoint. No write operations. No request body. No query parameters. Response is `text/event-stream`. Document the endpoint in the route module docstring (matches `main.py:1-10` style). |

### Known Threat Patterns for FastAPI SSE admin panel

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Information disclosure via error messages in DOM | Information Disclosure | HTML-escape all exception `str(e)` before rendering; prefer static "Service down" copy from UI-SPEC over raw exception text in the DOM. (UI-SPEC §Copywriting locks the per-service "down" copy.) |
| Information disclosure via config URLs in DOM | Information Disclosure | `_host_only()` helper strips scheme, credentials, and path — only `host:port` is ever rendered. Verified by grep: no `settings.*_token`, `settings.*_pass`, `settings.*_password`, `settings.*_secret` references in `admin.js` or the rendered HTML. |
| XSS via LLM/agent-influenced content | Tampering / XSS | Phase 40 has no LLM/agent content — only deterministic health-check results. The `escapeHtml` helper is still required because exception messages may contain untrusted strings (e.g. a CalDAV server returning an error body). |
| DoS via SSE generator stuck loop | Denial of Service | `await asyncio.sleep(45)` at the end of every generator cycle ensures the event loop can cancel the task on client disconnect. Per FastAPI docs: "An async task can only be cancelled when it reaches an await." [CITED: fastapi.tiangolo.com/advanced/custom-response/#streamingresponse] |
| DoS via slow backend blocking SSE | Denial of Service | `asyncio.wait_for(check, timeout=5)` caps each health check at 5s; `asyncio.gather(return_exceptions=True)` runs them concurrently so total is min(5s, sum) — never more than 5s. |
| Cross-Site Scripting via admin.html injection | Tampering / XSS | `admin.html` is a static file served by `StaticFiles` — no server-side templating, no user input rendered into HTML at serve time. All dynamic content is rendered client-side by `admin.js` with `textContent` / `escapeHtml`. |
| Unauthenticated access to system health details | Information Disclosure | D-08 explicitly accepts this risk: "LAN-only trust, same as the existing dashboard." The `/health` endpoint (`main.py:140-142`) already exposes `ollama_ready` without auth — the admin page is the same trust boundary. Document as accepted per ASVS L1. |
| Discoverability of admin URL | Information Disclosure | D-07/D-09 lock no discoverability — `index.html` MUST NOT link to `/admin`. Verification gate: `grep -n '/admin' services/nova-core/static/index.html` returns nothing. Mild obscurity on top of LAN trust, not a substitute for it. |

### Project Constraints (from CLAUDE.md / AGENTS.md)

> `./.claude/CLAUDE.md` exists (read in full). No `./AGENTS.md` exists. The CLAUDE.md content is largely project/stack/conventions documentation imported from `.planning/codebase/*.md`. The actionable directives the planner must honor:

| Directive | Source | How Phase 40 Honors It |
|-----------|--------|------------------------|
| Privacy: All reasoning and household data stay local; only WhatsApp (Meta) and Outlook (MS Graph) touch the public internet; never cloud-LLM calls | CLAUDE.md §Constraints | Phase 40 health checks all hit local services (Ollama, Postgres, CalDAV, HA on the docker network; IMAP is the only external touch but only does a login check, no data exfiltration). No new external network calls introduced. |
| Git-push-to-deploy via Coolify only — no manual production changes | CLAUDE.md §Constraints | Phase 40 is pure code — merged via the existing git-push deploy flow. No ops scripts, no manual DB migrations. |
| Python modules: lowercase, single word or short compound, no underhistorical prefixes | CLAUDE.md §Conventions | Helpers use `_check_*`, `_collect_*`, `_host_only`, `_mask_identifier` — snake_case, verb-first, underscore-prefixed for internal helpers (matches existing style). |
| Every module opens with a one-to-few-line docstring + `from __future__ import annotations` | CLAUDE.md §Conventions | New code added to `main.py` reuses the existing module docstring. No new module files in this phase. |
| Use `%s`-style lazy formatting in log calls, not f-strings | CLAUDE.md §Logging | `log.warning("admin SSE generator error: %s", e)` — NOT `log.warning(f"... {e}")` |
| Tool execution never raises to caller: wrap `fn(**kwargs)` in `try/except Exception` and return the error as a string | CLAUDE.md §Error Handling | Each `_check_*` helper wraps its inner call in `try/except Exception` and returns `{status: "down", detail: ...}` — never raises |
| `is_ready()`-style health checks swallow expected transient errors narrowly: catch the specific exception type, not bare `Exception` | CLAUDE.md §Error Handling | The admin check helpers catch broad `Exception` at the outermost level (because any failure means "down"), but inner calls (e.g. `llm.is_ready()`) already narrow their catches. This is consistent — the outer catch is for resilience, the inner catch is for diagnostic granularity. |
| FastAPI endpoints validate at the boundary and raise `HTTPException` directly for auth/validation failures | CLAUDE.md §Error Handling | No new `HTTPException` raises in `/admin/stream` — the SSE generator catches all exceptions internally and yields `status: "down"` (per existing `/dashboard/stream` pattern at `main.py:303-304`). |
| Inline comments mark stubs and future work explicitly with `# TODO(PhaseN): ...` | CLAUDE.md §Comments | If any admin functionality is stubbed (e.g. webhook diagnostics deferred per CONTEXT.md), use `# TODO(Phase 41): webhook health diagnostics` style. |
| No formatter/linter config — match existing style manually: 4-space indents, double quotes for strings, trailing commas in multi-line literals | CLAUDE.md §Code Style | New code matches the existing `main.py` / `app.js` / `style.css` style. |
| Bash scripts start with `set -euo pipefail` | CLAUDE.md §Code Style | No new bash scripts in this phase. |
| GSD workflow enforcement: use `/gsd-quick`, `/gsd-debug`, `/gsd-execute-phase` entry points; do not make direct repo edits outside a GSD workflow unless explicitly asked | CLAUDE.md §GSD Workflow Enforcement | Phase 40 is being executed via `/gsd-execute-phase` — compliant. |
| Use these entry points: `/gsd-quick` for small fixes, `/gsd-debug` for investigation, `/gsd-execute-phase` for planned phase work | CLAUDE.md §GSD Workflow Enforcement | Phase 40 work goes through the standard plan → execute → verify flow. |

## Runtime State Inventory

> Phase 40 is a greenfield addition — no rename, refactor, rebrand, string replacement, or migration of existing data. The Runtime State Inventory is therefore SKIPPED. Explicitly answering the canonical question: *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?*

- **Stored data:** None — no DB migrations, no schema changes, no new tables. The `channel_identities` and `user_preferences` tables already exist and are read-only from the admin's perspective.
- **Live service config:** None — no changes to n8n, Datadog, Tailscale, Cloudflare Tunnel, or any external service. The admin page reads `settings` from the nova-core process env (already loaded).
- **OS-registered state:** None — no new cron jobs, no Task Scheduler entries, no systemd units, no launchd plists.
- **Secrets and env vars:** None — no new secrets, no new env var names. The admin page reads existing `settings.*` values (already defined in `config.py:21-65`).
- **Build artifacts / installed packages:** None — no new packages, no new pip installs, no new Docker images. The existing `services/nova-core/Dockerfile` rebuilds `static/` on next deploy.

**Nothing found in any category — verified by reading `docker-compose.yml`, `services/nova-core/Dockerfile`, `services/nova-core/alembic/versions/`, and `services/nova-core/app/config.py` during this research session.**

## Sources

### Primary (HIGH confidence — codebase)
- `services/nova-core/app/main.py:281-307` — existing `/dashboard` redirect + `/dashboard/stream` SSE generator (template to clone)
- `services/nova-core/app/main.py:684-713` — existing `/api/preferences` query (template to extend for channel status)
- `services/nova-core/app/llm.py:85-92` — existing `is_ready()` Ollama health check (to reuse)
- `services/nova-core/app/db.py:15-19` — existing `get_pool()` asyncpg pool (to reuse)
- `services/nova-core/app/tools/calendar.py:20-26` — existing `_get_calendar()` (to reuse)
- `services/nova-core/app/tools/home_assistant.py:38-55` — existing `_ha_get()` (to reuse)
- `services/nova-core/app/tools/email.py:27-40` — existing `_get_imap_connection()` (to reuse)
- `services/nova-core/static/index.html` — existing dashboard HTML (template structure to clone)
- `services/nova-core/static/app.js:13-32,197-201` — existing dashboard JS (SSE + escapeHtml patterns to clone)
- `services/nova-core/static/style.css` — shared CSS (design tokens to reuse)
- `services/nova-core/requirements.txt` — pinned dependencies (no new packages needed)
- `services/nova-core/tests/test_dashboard.py` — existing test pattern (template to clone for `test_admin.py`)
- `.planning/phases/40-admin-panel-page/40-CONTEXT.md` — locked decisions D-01..D-10
- `.planning/phases/40-admin-panel-page/40-UI-SPEC.md` — visual/interaction contract
- `.planning/codebase/CONVENTIONS.md` — coding conventions (imported into CLAUDE.md)
- `.planning/codebase/ARCHITECTURE.md` — system architecture (imported into CLAUDE.md)

### Secondary (MEDIUM confidence — official docs)
- [CITED: fastapi.tiangolo.com/advanced/custom-response/#streamingresponse] — FastAPI StreamingResponse + async generator + cancellation semantics
- [CITED: developer.mozilla.org/en-US/docs/Web/API/EventSource] — EventSource API, readyState, auto-reconnect, named events, HTTP/1.1 6-connection limit (non-issue for Phase 40)
- [CITED: docs.python.org/3.12/library/asyncio-task.html] — `asyncio.gather(return_exceptions=True)`, `asyncio.wait_for(timeout=N)`, `asyncio.timeout()` context manager

### Tertiary (LOW confidence — none)
- None — no claims in this research rely solely on training data. Every external claim cites an official doc or the codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified present in `requirements.txt` and already used by existing endpoints
- Architecture: HIGH — every pattern cloned from a working existing endpoint in the same codebase
- Pitfalls: HIGH — derived from FastAPI/MDN/Python official docs + existing codebase patterns
- Security: MEDIUM — ASVS L1 with explicit accepted risk on auth (D-08); mitigations are standard (escapeHtml, _host_only, asyncio.wait_for)
- Validation: HIGH — existing pytest infrastructure in `tests/test_dashboard.py` provides the exact template

**Research date:** 2026-07-13
**Valid until:** 2026-08-12 (30 days — stable domain; FastAPI/Python/MDN docs change slowly, and the codebase patterns are frozen until the next refactor)
