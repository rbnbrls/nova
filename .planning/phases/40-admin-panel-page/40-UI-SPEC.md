---
phase: 40
slug: admin-panel-page
status: draft
shadcn_initialized: false
preset: not applicable
created: 2026-07-13
---

# Phase 40 — UI Design Contract

> Visual and interaction contract for the Nova admin panel page (`/admin` → `/static/admin.html`).
> A read-only status board mirroring the household dashboard's glass-panel aesthetic — system health + channel link status, pushed via SSE. No write actions, no auth, no discoverability.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none (vanilla HTML/CSS/JS — no component library) |
| Preset | not applicable |
| Component library | none — hand-built components in `static/admin.html` + `static/admin.js` |
| Icon library | emoji glyphs + `status-indicator` / `pulse-dot` CSS (consistent with existing dashboard) |
| Font | Body: 'Plus Jakarta Sans', Headings: 'Outfit' (loaded from Google Fonts, same as `index.html`) |

> Source: existing `static/style.css` design tokens. Phase 40 reuses the shared stylesheet and adds a small admin-specific block. `admin.html` and `admin.js` mirror the structure of `index.html` / `app.js`.

---

## Spacing Scale

Declared values (must be multiples of 4). All values already established in `style.css`; Phase 40 reuses them.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon gaps, inline dot/label spacing (`gap: 0.25rem` ≈ 4px) |
| sm | 8px | Compact badge padding, dot-to-label gap (`0.5rem` ≈ 8px) |
| md | 16px | Default element spacing within cards (`1rem` ≈ 16px) |
| lg | 24px | Section padding, card-to-card grid gap (`1.5rem` ≈ 24px) |
| xl | 32px | Layout gaps in `dashboard-container` (`2rem` ≈ 32px) |
| 2xl | 48px | Reserved for major section breaks — not expected in Phase 40 |
| 3xl | 64px | Page-level spacing — not expected in Phase 40 |

Exceptions: none. Admin page reuses the `.dashboard-container` 2rem outer padding and `.dashboard-grid` 2rem gap.

---

## Typography

Phase 40 introduces no new type roles. All sizes already in `style.css`:

| Role | Size | Weight | Line Height | Source |
|------|------|--------|-------------|--------|
| Body | 15px (`0.95rem`) | 400 regular | 1.5 | `.todo-title`, `.chat-message-text`, `.status-container` |
| Label / meta | 13px (`0.8rem`) | 600 | 1.3 | `.event-meta`, `.audit-time`, `.status-indicator` |
| Heading | 24px (`1.5rem`) | 600 | 1.2 | `.card-header h2` — used for each admin card title |
| Display | 35px (`2.2rem`) | 800 | 1.1 | `.logo-area h1` — admin page title "Nova Admin" |

> Phase 40 must NOT add a fifth size or a third weight. Health-card service names use the Body role (15px) with weight 600 inline — keep within the 2-weight rule by reusing 600 rather than introducing 500 for a single element.

---

## Color

Phase 40 reuses the existing CSS variables verbatim. No new colors. The 60/30/10 split below maps the admin page surface allocation:

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#0b0f19` (`--bg-color`) | Page background + radial-gradient overlay |
| Secondary (30%) | `rgba(17, 24, 39, 0.7)` (`--panel-bg`) | Glass-panel cards for each service / channel status block |
| Accent (10%) | `#8b5cf6` / `#a78bfa` (`--accent-color` / `--accent-light`) | See reserved-for list below |
| Destructive / Down | `#ef4444` (`--warning-color`) | Red health indicator dot + "unreachable" error state copy + `--warning-bg` tile tint |
| Healthy | `#10b981` (`--success-color`) | Green health indicator dot + "linked" channel badge |

Accent reserved for:
- Admin page logo highlight (the "Admin" word after "Nova" — matches dashboard `<span>` pattern)
- Active tab underline/fill if a per-user channel-status tab selector is used
- `.badge-accent` count badges next to card headers
- Focus ring on the single "Back to Dashboard" link (via `--accent-light`)
- Healthy `.pulse-dot` ring color is green (per existing keyframes) — accent purple is NOT used for status dots

Accent is NOT used for: status dots (those use success/warning tokens), body text, panel backgrounds, or large fill regions.

---

## Copywriting Contract

Phase 40 is fundamentally read-only — D-04 locks "no write actions." The "CTA" role is filled only by the Back-to-Dashboard navigation link.

| Element | Copy |
|---------|------|
| Page title (display) | `Nova Admin` (with `Admin` in accent purple span, matching dashboard `Nova Household` pattern) |
| Page subtitle / status indicator | `Live Connection` (reuse `.status-indicator` + `.pulse-dot` from dashboard header) |
| Primary CTA | `← Back to Dashboard` — text link in header right side, accent on hover. No primary `btn-primary` because no write action exists. |
| Empty state heading | `Waiting for status…` |
| Empty state body | `Connecting to admin stream…` (mirrors existing `placeholder-loader` pattern: "Connecting to task feed…", "Syncing calendar…") |
| Error state (page-level SSE failure) | `Admin stream disconnected. Retrying…` — in `.chat-error`-style banner; JS auto-reconnect via `EventSource` (browser-native) |
| Error state (per-service unreachable) | Diagnostic copy in the card, format: `{Service Name}: unreachable` in destructive color, plus inline detail line: `Check {service} is running at {url}` where `{url}` is redacted to host:port (per untrusted-input-boundary guidance — never expose full config strings) |
| Loading state (initial fetch) | Each service card shows `.placeholder-loader` with text `Checking {Service Name}…` until first SSE payload arrives |
| Destructive confirmation | none — Phase 40 has zero destructive actions (D-04) |
| Channel status — linked | `Linked · {identifier}` (e.g. `Linked · +31 6 12 … 8`) — identifier masked per privacy scope; reuse existing masking from `/api/preferences` |
| Channel status — unlinked | `Not linked` in `--text-secondary` with no badge |
| Service status — healthy | `Ready` (Ollama) / `Connected` (Postgres, IMAP) / `Reachable` (CalDAV, HA) — green `.pulse-dot` + the service-specific detail below |
| Service status — down | `Unreachable` (CalDAV, HA) / `Disconnected` (Postgres, IMAP) / `Not ready` (Ollama) — red static dot (NO pulse keyframe — pulse is reserved for healthy state only) |

Per-service detail lines (shown under the status word, in `--text-secondary` meta text):

| Service | Healthy detail | Down detail |
|---------|---------------|-------------|
| Ollama | `Model: qwen3:14b` | `Ollama not responding at {host}` |
| Postgres | `{N} tables reachable` | `Cannot acquire pool at {host}` |
| CalDAV | `Calendar URL reachable` | `Check CalDAV server at {host}` |
| Home Assistant | `HA reachable` | `Check HA at {host}` |
| Email (IMAP) | `{redacted_address}` | `IMAP login failed at {host}` |

> `{host}` MUST be derived from config (host + port only, never the full URL with credentials). Per `references/untrusted-input-boundary.md`, no token/password/auth_header is ever rendered to the DOM.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable — vanilla HTML project, no shadcn |
| (third-party) | none | not applicable |

No registries are in scope for this phase. No `npx shadcn view` vetting required.

---

## Layout & Interaction Contract

Detailed enough that the executor can build `admin.html` + `admin.js` without further design questions. These rules are non-negotiable unless re-discussed:

### Page Structure
1. **Container:** Reuse `.dashboard-container` (max-width 1600px, 2rem padding, vertical flex with 2rem gap).
2. **Header:** Reuse `.dashboard-header` with `.logo-area` (h1 = `Nova <span>Admin</span>`, then `.status-indicator` with `.pulse-dot` + `Live Connection`) and a right-side `.time-area` containing the live clock only — NO settings cog on the admin page (admin is read-only). Replace the cog with a `← Back to Dashboard` text link styled as `.btn-secondary` (small, ~0.9rem) for usability per D-discretion recommendation.
3. **Main grid:** Use `.dashboard-grid` (2-column on desktop ≥1024px, single column below). Two-stack layout:
   - **Top row:** `System Status` card (spans 2 columns via the existing `grid-column: span 2` pattern used by `.chat-panel` / `.audit-panel`) containing a 5-cell inner grid (3 columns on wide screens, 2 below 1200px, 1 below 800px) — one cell per service: Ollama, Postgres, CalDAV, Home Assistant, Email (IMAP).
   - **Bottom row:** `Channel Status` card (spans 2 columns) with a per-user tab selector (`.chat-user-tab` pattern: `Ruben` / `Méral` — NO `Household` tab since channel linking is per-user) above a 2-column grid: WhatsApp cell + Telegram cell.

### Service Status Cell (inner card)
Each cell is a `.glass-panel`-lite block (NOT a full `.dashboard-card` to avoid double-glass-nesting) — use a flat `rgba(255, 255, 255, 0.02)` panel with `1px solid rgba(255,255,255,0.05)` border and 12px radius (matches `.assignee-section` / `.event-item` styling). Cell contents:
1. Service name — Body 15px / weight 600
2. Status dot (8px circle, green `.pulse-dot` OR red static dot — same `.pulse-dot` element but toggle the `--warning-color` background class)
3. Status word — 13px label, weight 600, green or destructive color
4. Detail line — 13px meta, `--text-secondary`

### Channel Status Cell
Per-user, per-channel. Reuse `.assignee-section` visual pattern:
- WhatsApp cell: border-left 3px accent (`--accent-color`), header `WhatsApp` then `.status-container` line: `Status:` label + `.status-value` (`Linked · {masked}` or `Not linked`)
- Telegram cell: same pattern, border-left accent
- When unlinked, the border-left fades to `--text-secondary` (mirrors `.assignee-section.household` pattern)

### SSE / Refresh Interaction
- `admin.js` opens a single `EventSource('/admin/stream')` — match D-10's preferred approach (new endpoint, not overloaded `/dashboard/stream`).
- The endpoint emits `event: status` with a JSON payload: `{"services": {...}, "channels": {...}}` every **45 seconds** (midpoint of the 30–60s discretion range — balances freshness vs. ping load on 5 backends).
- On each event, `admin.js` re-renders every cell. Unchanged cells MUST keep their existing DOM (no flash/re-animation) — only changed cells swap content + animate via existing `@keyframes fadeIn`.
- On `EventSource` `onerror`, show the page-level error banner (`.chat-error` styling) `Admin stream disconnected. Retrying…` — browser auto-reconnects; do NOT throw a modal.
- Initial mount: each service cell renders `Checking {Service Name}…` placeholder until first event arrives (target ≤45s tolerance; show a subtle `pulse` animation on the placeholder text using the existing `.chat-loading` `pulse` keyframe).

### No-Discoverability Contract (D-07, D-09)
- `index.html` (dashboard) MUST NOT gain a link, button, or footer reference to `/admin`. Phase 40 only adds admin.html/admin.js + backend route. Editor must verify `index.html` diff is empty.
- `admin.html` SHOULD link back to the dashboard (Back to Dashboard) for usability — this is allowed because it does not make `/admin` discoverable from the public dashboard.

### Accessibility
- Status dots MUST have an `aria-label` on the parent cell (e.g. `aria-label="Ollama: Ready"`) — color alone is not an adequate status signal.
- Each `.pulse-dot` green dot pairs with the textual status word; the dot is decorative (`aria-hidden="true"` on the `<span>`).
- The Back-to-Dashboard link is a real `<a href="/">` (not a JS click handler) so it works without JS and is keyboard-focusable.

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending