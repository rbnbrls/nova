"""Nova Core — FastAPI entrypoint.

Exposes:
  GET  /health                     liveness + Ollama readiness
  POST /v1/chat/completions        OpenAI-compatible agent endpoint (all channels)
  GET  /dashboard/tasks            read-only feed for the Phase 8 dashboard (stub)
  GET  /dashboard/events           read-only feed for the Phase 8 dashboard (stub)
  GET  /admin                      redirect to static admin page (D-05)
  GET  /admin/stream               unauthenticated SSE health feed (D-08, D-10)

Channel webhooks (WhatsApp, Phase 4) will be added under /webhooks/*.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import zoneinfo

from fastapi import FastAPI, Request, Query, BackgroundTasks, Response, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import admin_models, llm, db
from .agent import run_agent
from .config import get_active_model_sync, set_active_model, settings
from .models import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice, RequestCodeRequest, VerifyCodeRequest, BriefingSettingsRequest, DNDSettingsRequest, LinkWhatsAppStartRequest, LinkWhatsAppVerifyRequest, LinkTelegramStartRequest, LinkTelegramVerifyRequest, DashboardChatRequest, ModelSwitchRequest, ModelPullRequest, ModelDeleteRequest, validate_model_name
from .security import verify_whatsapp_signature, verify_telegram_signature
from .channels.whatsapp import process_incoming_whatsapp, send_whatsapp_otp
from .channels.telegram import process_incoming_telegram, _handle_telegram_command, send_telegram_otp
from .channels.webhook_router import register_all_webhooks
from .db import get_pool as db_get_pool
from .tools.calendar import _get_calendar
from caldav.lib.error import AuthorizationError
from .tools.email import _get_imap_connection
from .tools.home_assistant import _ha_get
from .voice_rooms import RoomSessionManager
from .contacts_sync import sync_all_contacts as _carddav_sync_all

from .scheduler import check_new_emails, send_morning_briefing, check_overdue_tasks, check_at_risk_tasks, run_briefing_scheduler, process_queued_notifications, run_maintenance_dep_scan, run_maintenance_log_anomaly, run_maintenance_backup_verify, run_maintenance_trend_report

log = logging.getLogger("nova-core")

voice_room_manager: RoomSessionManager | None = None


async def _periodic_task(name: str, interval_sec: int, coro_fn, *args, **kwargs):
    """Run an async function periodically with a fixed delay between executions.
    
    Replaces APScheduler AsyncIOScheduler which causes a process crash
    in Python 3.12 when scheduler.start() is called (segfault or OOM).
    This implementation uses a simple asyncio loop and catches all
    exceptions to avoid crashing the process.
    
    The first execution is delayed by 90 seconds to give the application
    time to fully initialize before any background work begins.
    """
    try:
        await asyncio.sleep(90)
    except asyncio.CancelledError:
        return
    while True:
        try:
            await coro_fn(*args, **kwargs)
        except Exception as exc:
            log.warning("Periodic task %s failed: %s: %s", name, type(exc).__name__, exc)
        try:
            await asyncio.sleep(interval_sec)
        except asyncio.CancelledError:
            break


async def _start_background_tasks():
    """Start all periodic background tasks as asyncio tasks.
    
    Called from the lifespan handler. Each task runs independently;
    a failure in one does not affect the others (D-02 isolation).
    """
    tasks = [
        _periodic_task("check_new_emails", 300, check_new_emails),
        _periodic_task("run_briefing_scheduler", 60, run_briefing_scheduler),
        _periodic_task("process_queued_notifications", 60, process_queued_notifications),
        _periodic_task("check_at_risk_tasks", 3600, check_at_risk_tasks),
    ]
    if settings.maintenance_enabled:
        # Maintenance jobs run on cron-like schedule (checked every 60s)
        async def _maintenance_tick():
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            hour = now.hour
            day = now.weekday()
            if hour == 2 and now.minute == 0:
                await run_maintenance_dep_scan()
            if hour == 3 and now.minute == 0:
                await run_maintenance_log_anomaly()
            if hour == 4 and now.minute == 0:
                await run_maintenance_backup_verify()
            if hour == 5 and now.minute == 0 and day == 6:
                await run_maintenance_trend_report()
        tasks.append(_periodic_task("maintenance_tick", 60, _maintenance_tick))
    
    for task_coro in tasks:
        try:
            t = asyncio.create_task(task_coro)
            t.add_done_callback(_handle_task_exception)
        except Exception as e:
            log.warning("Failed to start background task: %s", e)


def _handle_task_exception(task: asyncio.Task) -> None:
    """Log any unhandled exception from a background asyncio task.
    
    Without this callback, an exception in an asyncio.create_task() would
    be silently swallowed until garbage-collected, at which point Python
    logs "Task exception was never retrieved". This callback surfaces the
    error immediately at WARNING level (D-02: never crash from a background
    task failure).
    """
    try:
        exc = task.exception()
        if exc is not None:
            log.warning("Background task %s raised: %s: %s",
                        task.get_name(), type(exc).__name__, exc)
    except asyncio.CancelledError:
        pass  # Task was cancelled — not an error.

# WhoAmI intent detection: matches "I'm Ruben", "I am Méral", "Nova, this is Ruben", etc.
_WHOAMI_PATTERN = re.compile(
    r"^(?:nova,?\s+)?(?:i'?m |i am |this is |it'?s )(r(u|e)ben|m[eé]ral)$"
    r"|^(?:nova,?\s+)?(r(u|e)ben|m[eé]ral) speaking$",
    re.IGNORECASE
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool and run migrations
    await db.get_pool()
    await db.run_migrations()
    
    # Initialize voice room session manager
    pool = await db.get_pool()
    global voice_room_manager
    voice_room_manager = RoomSessionManager(pool, ttl_minutes=30)
    
    # DIAGNOSTIC: no background tasks, no scheduler — minimal lifespan
    log.info("Lifespan: database + migrations complete, voice_room_manager initialized")

    # Register Telegram bot command menu if enabled
    if settings.nova_telegram_enabled and settings.telegram_bot_token:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                commands_payload = {
                    "commands": [
                        {"command": "help", "description": "Show what Nova can do"},
                        {"command": "tasks", "description": "Show your current tasks"},
                        {"command": "settings", "description": "Manage your preferences"},
                    ]
                }
                resp = await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/setMyCommands",
                    json=commands_payload
                )
                if resp.status_code == 200:
                    log.info("Telegram command menu registered")
                else:
                    log.warning("Telegram command registration failed: %s", resp.status_code)
        except Exception as e:
            log.warning("Telegram command registration error: %s", e)
    
    yield
    # Close database pool
    # Background asyncio tasks are cancelled automatically by the event loop shutdown
    try:
        await db.close_pool()
    except Exception as e:
        log.warning("DB pool close error: %s", e)


async def _carddav_startup_sync() -> None:
    try:
        result = await _carddav_sync_all()
        log.info("CardDAV startup sync complete: %s", result)
    except Exception as exc:
        log.warning("CardDAV startup sync failed (non-fatal): %s", exc)


app = FastAPI(title="Nova Core", version="0.1.0", lifespan=lifespan)

# Register channel webhook routes via adapter pattern
try:
    asyncio.get_running_loop()
except RuntimeError:
    # No running event loop — safe to run_until_complete at module load
    asyncio.run(register_all_webhooks(app))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama_ready": await llm.is_ready()}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest, request: Request, user: str | None = None, room: str | None = None) -> ChatCompletionResponse:
    """Run the agent loop for the latest user message and return the reply."""
    if settings.nova_api_token:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], settings.nova_api_token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    resolved_room = room or req.room or "default"
    history = [m.model_dump() for m in req.messages[:-1]]
    last = req.messages[-1].content if req.messages else ""

    # WhoAmI intent detection: check if the message is an identity claim
    if last and voice_room_manager is not None:
        m = _WHOAMI_PATTERN.match(last.strip())
        if m:
            claimed = (m.group(1) or m.group(3)).lower()
            # Normalize to DB spelling
            if claimed.startswith("m"):
                claimed = "Meral"
            elif claimed.startswith("r"):
                claimed = "Ruben"
            await voice_room_manager.set_active_user(resolved_room, claimed)
            return ChatCompletionResponse(
                model=req.model or settings.nova_model,
                choices=[Choice(message=ChatMessage(role="assistant", content=f"Okay {claimed}, I will remember you for this room."))],
            )

    # Resolve user: explicit query/user param takes precedence, otherwise resolve from room
    resolved_user = user or req.user or "household"
    if resolved_room != "default" and resolved_user == "household" and voice_room_manager is not None:
        resolved_user = await voice_room_manager.get_active_user(resolved_room)

    try:
        reply = await run_agent(last, user=resolved_user, history=history, channel="api")
    except Exception as e:
        log.error("Agent loop failed: %s", e)
        reply = "Nova is having trouble right now, please try again later."

    return ChatCompletionResponse(
        model=req.model or settings.nova_model,
        choices=[Choice(message=ChatMessage(role="assistant", content=reply))],
    )


# --- Dashboard feeds (Phase 8; real queries land with Phase 5 data tools) ---


@app.get("/dashboard/tasks")
async def dashboard_tasks() -> dict:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.due_at, t.priority, t.planning_state,
                   t.labels, t.is_template, t.template_id, t.created_at,
                   u.name as assignee
            FROM tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            WHERE t.status = 'active'
            ORDER BY t.due_at ASC NULLS LAST, t.created_at ASC
            """
        )

    task_ids = [str(r["id"]) for r in rows]
    note_counts: dict[str, int] = {}
    blocker_titles: dict[str, list[str]] = {}
    if task_ids:
        note_rows = await conn.fetch(
            "SELECT task_id, COUNT(*) as cnt FROM task_notes WHERE task_id = ANY($1::uuid[]) GROUP BY task_id",
            task_ids,
        )
        for nr in note_rows:
            note_counts[str(nr["task_id"])] = nr["cnt"]

        dep_rows = await conn.fetch(
            """
            SELECT td.child_id, t.title as blocker_title
            FROM task_dependencies td
            JOIN tasks t ON t.id = td.parent_id
            WHERE td.child_id = ANY($1::uuid[])
            """,
            task_ids,
        )
        for dr in dep_rows:
            cid = str(dr["child_id"])
            blocker_titles.setdefault(cid, []).append(dr["blocker_title"])

    tasks = []
    now_utc = datetime.now(timezone.utc)
    for r in rows:
        tid = str(r["id"])
        due_iso = r["due_at"].isoformat() if r["due_at"] else None
        tasks.append({
            "id": tid,
            "title": r["title"],
            "due_at": due_iso,
            "priority": r["priority"] or "medium",
            "assignee": r["assignee"] or "unassigned",
            "labels": r["labels"] or [],
            "is_template": r["is_template"] or False,
            "template_id": str(r["template_id"]) if r["template_id"] else None,
            "planning_state": r["planning_state"],
            "note_count": note_counts.get(tid, 0),
            "blocked_by": blocker_titles.get(tid, []),
            "overdue": r["due_at"] is not None and r["due_at"] < now_utc - timedelta(hours=48),
        })
    return {"tasks": tasks}


@app.get("/dashboard/events")
async def dashboard_events() -> dict:
    from datetime import datetime, timezone, timedelta
    import zoneinfo

    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    start_dt = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=tz)
    end_dt = start_dt + timedelta(days=7)
    
    try:
        calendar = await asyncio.to_thread(_get_calendar)
        events = await asyncio.to_thread(calendar.search, start=start_dt, end=end_dt, event=True, expand=True)
    except Exception as e:
        log.warning("Failed to fetch calendar for dashboard: %s", e)
        return {"events": []}
        
    events_list = []
    for ev in events:
        vevent = ev.vobject_instance.vevent
        summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
        dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
        dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None
        location = vevent.location.value if hasattr(vevent, "location") and vevent.location.value else ""
        rrule_raw = vevent.rrule.value if hasattr(vevent, "rrule") else None
        rrule_str = str(rrule_raw) if rrule_raw else None
        uid = str(vevent.uid.value) if hasattr(vevent, "uid") else ""
        events_list.append({
            "title": summary,
            "start": dtstart.isoformat() if dtstart else "",
            "end": dtend.isoformat() if dtend else "",
            "location": location,
            "rrule": rrule_str,
            "uid": uid,
        })
    return {"events": events_list}


@app.get("/dashboard/audit")
async def dashboard_audit(limit: int = 50) -> dict:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, created_at, user_name, tool_name, action_summary, status, confirmation_required
            FROM audit_log
            WHERE created_at > now() - interval '90 days'
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    entries = []
    for r in rows:
        entries.append({
            "id": r["id"],
            "timestamp": r["created_at"].isoformat(),
            "user_name": r["user_name"],
            "tool_name": r["tool_name"],
            "action_summary": r["action_summary"],
            "status": r["status"],
            "confirmation_required": r["confirmation_required"],
        })
    return {"audit": entries}


@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/static/index.html")


@app.get("/dashboard/availability")
async def dashboard_availability(days: int = 7):
    """Return day-by-day availability summary for the next N days (working hours 08:00-22:00)."""
    from datetime import date
    from .planning import WORK_DAY_START as _WS, WORK_DAY_END as _WE, _merge_slots, TimeSlot

    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    today = date.today()
    start_date = today
    end_date = today + timedelta(days=days)

    try:
        cal = await asyncio.to_thread(_get_calendar)
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        events = await asyncio.to_thread(cal.search, start=start_dt, end=end_dt, event=True, expand=True)
    except Exception as e:
        log.warning("Failed to fetch calendar for availability: %s", e)
        return {"availability": []}

    occupied: list[TimeSlot] = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            ds = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            de = vevent.dtend.value if hasattr(vevent, "dtend") else None
            if ds and de and isinstance(ds, datetime) and isinstance(de, datetime):
                occupied.append(TimeSlot(start=ds, end=de))
        except Exception:
            continue

    merged = _merge_slots(occupied)
    work_min = int((_WE - _WS) * 60)

    availability = []
    current = start_date
    while current <= end_date:
        day_start = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WS)
        day_end = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WE)
        occ_min = 0
        for o in merged:
            if o.end <= day_start or o.start >= day_end:
                continue
            o_start = max(o.start, day_start)
            o_end = min(o.end, day_end)
            occ_min += (o_end - o_start).total_seconds() / 60
        free_min = max(0, work_min - occ_min)
        pct = round((free_min / work_min) * 100, 1) if work_min > 0 else 0
        availability.append({
            "date": current.isoformat(),
            "free_minutes": int(free_min),
            "occupied_minutes": int(occ_min),
            "free_percent": pct,
        })
        current += timedelta(days=1)

    return {"availability": availability}


@app.get("/dashboard/find-slot")
async def dashboard_find_slot(duration_min: int = 30, days: int = 7):
    """Find available time slots for a given duration in the next N days."""
    from datetime import date
    from .planning import WORK_DAY_START as _WS, WORK_DAY_END as _WE, _merge_slots, TimeSlot

    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    today = date.today()
    start_date = today
    end_date = today + timedelta(days=days)

    try:
        cal = await asyncio.to_thread(_get_calendar)
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        events = await asyncio.to_thread(cal.search, start=start_dt, end=end_dt, event=True, expand=True)
    except Exception as e:
        log.warning("Failed to fetch calendar for find-slot: %s", e)
        return {"slots": []}

    occupied: list[TimeSlot] = []
    for ev in events:
        try:
            vevent = ev.vobject_instance.vevent
            ds = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            de = vevent.dtend.value if hasattr(vevent, "dtend") else None
            if ds and de and isinstance(ds, datetime) and isinstance(de, datetime):
                occupied.append(TimeSlot(start=ds, end=de))
        except Exception:
            continue

    merged = _merge_slots(occupied)

    slots = []
    current = start_date
    while current <= end_date:
        day_start = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WS)
        day_end = datetime.combine(current, datetime.min.time(), tzinfo=tz).replace(hour=_WE)
        cursor = day_start
        for o in merged:
            if o.end <= cursor or o.start >= day_end:
                continue
            if o.start > cursor:
                gap_end = min(o.start, day_end)
                gap_min = (gap_end - cursor).total_seconds() / 60
                if gap_min >= duration_min:
                    slots.append({
                        "date": current.isoformat(),
                        "start": cursor.strftime("%H:%M"),
                        "end": gap_end.strftime("%H:%M"),
                        "duration_min": int(gap_min),
                    })
            cursor = max(cursor, o.end)
            if cursor >= day_end:
                break
        if cursor < day_end:
            gap_min = (day_end - cursor).total_seconds() / 60
            if gap_min >= duration_min:
                slots.append({
                    "date": current.isoformat(),
                    "start": cursor.strftime("%H:%M"),
                    "end": day_end.strftime("%H:%M"),
                    "duration_min": int(gap_min),
                })
        current += timedelta(days=1)

    return {"slots": slots}


@app.get("/dashboard/plan/{user}")
async def dashboard_plan(user: str, start: str | None = None, end: str | None = None, regenerate: bool = False):
    """Return a time-blocked plan for *user* as JSON."""
    from .planning import generate_plan as planner_generate
    start_date = datetime.fromisoformat(start).date() if start else date.today()
    end_date = datetime.fromisoformat(end).date() if end else start_date
    blocks = await planner_generate(user, start_date, end_date, regenerate)
    return {"blocks": [b.__dict__ for b in blocks]}


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
                availability_data = await dashboard_availability(days=7)
                payload = {
                    "tasks": tasks_data["tasks"],
                    "events": events_data["events"],
                    "audit": audit_data["audit"],
                    "availability": availability_data["availability"],
                }
                try:
                    from .planning import load_blocks
                    from datetime import date, timedelta
                    pool = await db.get_pool()
                    planned_rows = await load_blocks(pool, "household", date.today(), date.today() + timedelta(days=7))
                    payload["plan"] = [
                        {
                            "title": b.title,
                            "start": b.start_time.isoformat() if b.start_time else "",
                            "end": b.end_time.isoformat() if b.end_time else "",
                            "task_id": str(b.task_id) if b.task_id else None,
                        }
                        for b in planned_rows
                    ]
                except Exception:
                    payload["plan"] = []

                try:
                    from .replanning import get_at_risk_tasks as _get_at_risk, compute_next_best_action as _compute_nba
                    risk_by_user = {}
                    for u in ("Ruben", "Meral"):
                        tasks = await _get_at_risk(u, lookahead_days=7)
                        if tasks:
                            risk_by_user[u] = tasks[:5]
                    payload["at_risk"] = risk_by_user
                    house_next = await _compute_nba("household")
                    payload["next_action"] = house_next
                except Exception:
                    payload["at_risk"] = {}
                    payload["next_action"] = {"has_next_action": False}

                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                log.warning("SSE generator error: %s", e)
            await asyncio.sleep(15)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Admin status board — Phase 40 / Plan 01 (read-only, no auth per D-08)
# ---------------------------------------------------------------------------


def _host_only(url: str) -> str:
    """Return only ``host:port`` of a URL — never scheme, user, pass, or path.

    D-05 (privacy scope): admin payload ``host`` fields must never carry
    credentials.  ``urlparse().netloc`` still includes ``user:pass@`` so we
    rebuild from ``.hostname``/``.port``.  Schemeless inputs (e.g.
    ``"host:5432"``) leave the whole string in ``path`` with no netloc —
    we return the raw input in that case.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.hostname:
        if parsed.port:
            return f"{parsed.hostname}:{parsed.port}"
        return parsed.hostname
    # No scheme: urlparse put the whole thing in `path`.  Return as-is.
    return url


def _mask_identifier(number: str) -> str:
    """Mask a phone number-ish identifier as `+XX X XX … X` (D-03 privacy).

    Short values (<=7 digits after the leading +) are returned as-is —
    they cannot meaningfully identify a person.  The head is grouped as
    [2, 1, 3] digits so a Dutch mobile number reads `+31 6 12X … X`,
    matching the spacing already used by the dashboard preferences view
    (app.js).  The full identifier is replaced by its last digit.
    """
    if not number:
        return ""
    n = number.lstrip("+")
    if len(n) <= 7:
        return f"+{n}"
    head = f"{n[0:2]} {n[2:3]} {n[3:6]}"
    return f"+{head} … {n[-1]}"


async def _check_ollama() -> dict:
    """Ollama health check — includes active model + loading state + local models.

    Returns extended payload with ``model.active``, ``model.loading``,
    ``model.loading_name``, and top-level ``models`` (local model list).
    Auto-clears the loading flag when the target model is detected as
    locally available (D-05).
    """
    host = _host_only(settings.ollama_base_url)
    try:
        ready = await llm.is_ready()
        if not ready:
            return {
                "status": "down",
                "detail": f"Ollama not responding at {host}",
                "host": host,
                "model": {"active": "", "loading": False, "loading_name": ""},
                "models": [],
            }

        local_models = await admin_models.list_models()
        active_model = get_active_model_sync()
        loading_model = admin_models.get_loading_model()

        # Auto-clear: if the loading model is now listed locally, clear the
        # flag so the frontend modal auto-closes (D-05).
        if loading_model and any(m.get("name") == loading_model for m in local_models):
            admin_models.set_loading_model(None)
            loading_model = None

        status = "loading" if loading_model else "ok"
        detail = f"Model: {active_model}"

        return {
            "status": status,
            "detail": detail,
            "host": host,
            "model": {
                "active": active_model,
                "loading": bool(loading_model),
                "loading_name": loading_model or "",
            },
            "models": local_models,
        }
    except Exception as exc:
        log.warning("admin _check_ollama failed: %s", exc)
        return {
            "status": "down",
            "detail": f"Ollama not responding at {host}",
            "host": host,
            "model": {"active": "", "loading": False, "loading_name": ""},
            "models": [],
        }


async def _check_postgres() -> dict:
    """Postgres health check — reuses db.get_pool()."""
    host = f"{settings.postgres_host}:{settings.postgres_port}"
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
            table_count = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"
            )
        return {"status": "ok", "detail": f"{table_count} tables reachable", "host": host}
    except Exception as exc:
        log.warning("admin _check_postgres failed: %s", exc)
        return {"status": "down", "detail": f"Cannot acquire pool at {host}", "host": host}


async def _check_caldav() -> dict:
    """CalDAV health check — runs sync _get_calendar() in a thread pool.

    Wraps the synchronous CalDAV call in asyncio.to_thread so it does not
    block the event loop.  The asyncio.wait_for(timeout=5) in
    _collect_admin_status can then properly cancel the task if Radicale
    is unreachable or slow to respond.
    """
    host = _host_only(settings.caldav_url)
    try:
        await asyncio.to_thread(_get_calendar)
        return {"status": "ok", "detail": "Calendar URL reachable", "host": host}
    except AuthorizationError:
        log.warning("admin _check_caldav auth failed")
        return {
            "status": "down",
            "detail": f"Check CalDAV server at {host} — Unauthorized — check CalDAV credentials or server auth config",
            "host": host,
        }
    except asyncio.CancelledError:
        log.warning("admin _check_caldav cancelled (timeout)")
        return {"status": "down", "detail": f"CalDAV check timed out at {host}", "host": host}
    except Exception as exc:
        log.warning("admin _check_caldav failed: %s [%s]", type(exc).__name__, exc)
        hint = str(exc).split(":")[-1].strip()[:80] if str(exc) else ""
        detail = f"Check CalDAV server at {host}"
        if hint:
            detail += f" — {hint}"
        return {"status": "down", "detail": detail, "host": host}


async def _check_ha() -> dict:
    """Home Assistant health check — reuses async _ha_get('/').

    Distinguishes "not configured" (empty token/url) from "configured but
    unreachable" by inspecting the error payload returned by _ha_get.
    """
    host = _host_only(settings.nova_ha_url)
    try:
        result = await _ha_get("/")
        if isinstance(result, dict) and "error" in result:
            err = str(result.get("error", ""))
            if "not configured" in err.lower():
                return {"status": "down", "detail": "HA not configured", "host": host}
            return {"status": "down", "detail": f"Check HA at {host}", "host": host}
        return {"status": "ok", "detail": "HA reachable", "host": host}
    except Exception as exc:
        log.warning("admin _check_ha failed: %s", exc)
        return {"status": "down", "detail": f"Check HA at {host}", "host": host}


async def _check_imap() -> dict:
    """IMAP health check — reuses async _get_imap_connection().

    None return means "not configured" (empty nova_imap_host).  Otherwise
    the connection already succeeded (login happened inside the helper);
    we close it defensively before returning.
    """
    host = _host_only(settings.nova_imap_host)
    conn = None
    try:
        conn = await _get_imap_connection()
        if conn is None:
            return {"status": "down", "detail": "Not configured", "host": ""}
        # The user identifier is an email address — not a secret.  Mask to
        # `user@…` (domain removed) for consistency with the dashboard preferences view.
        user = settings.nova_imap_user or ""
        if "@" in user:
            user = user.split("@", 1)[0] + "@…"
        return {"status": "ok", "detail": user or "IMAP reachable", "host": host}
    except Exception as exc:
        log.warning("admin _check_imap failed: %s", exc)
        return {"status": "down", "detail": f"IMAP login failed at {host}", "host": host}
    finally:
        if conn is not None:
            try:
                # aioimaplib IMAP4_SSL — logout is the documented teardown.
                await conn.logout()
            except Exception:
                # Cleanup must never raise into the response path.
                pass


async def _collect_admin_status() -> dict:
    """Run all 5 service checks concurrently + the channel-link query.

    Uses asyncio.gather(return_exceptions=True) so one failing check does
    not abort the others (D-02 isolation).  Each check is capped at 5s via
    asyncio.wait_for so a hung backend adds ≈5s to the cycle rather than
    blocking the SSE generator indefinitely (T-40-06).
    """
    checks = [
        asyncio.wait_for(_check_ollama(), timeout=5),
        asyncio.wait_for(_check_postgres(), timeout=5),
        asyncio.wait_for(_check_caldav(), timeout=5),
        asyncio.wait_for(_check_ha(), timeout=5),
        asyncio.wait_for(_check_imap(), timeout=5),
    ]
    results = await asyncio.gather(*checks, return_exceptions=True)

    keys = ("ollama", "postgres", "caldav", "ha", "email")
    services: dict[str, dict] = {}
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            log.warning("admin %s check raised: %s %s", key, type(result).__name__, result)
            services[key] = {
                "status": "down",
                "detail": f"{key} check failed ({type(result).__name__})",
                "host": "",
            }
        else:
            services[key] = result

    channels = await _collect_channel_status()

    # Phase 41 — model pull progress
    pulling_tasks = await admin_models.get_all_pull_tasks()
    models_payload = {
        "pulling": [
            {"name": t.model, "status": t.status, "progress": t.progress, "message": t.message}
            for t in pulling_tasks
        ],
    }
    return {"services": services, "channels": channels, "models": models_payload}


async def _collect_channel_status() -> dict:
    """Per-user per-channel link state for Ruben and Meral (D-03).

    LEFT JOIN channel_identities on (user_id AND channel='telegram') so a
    missing Telegram row does not drop the user.  WhatsApp state lives on
    user_preferences.whatsapp_number (legacy column from Phase 13).
    """
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
    channels: dict[str, dict] = {}
    for r in rows:
        name = r["name"]
        channels_enabled = r["channels_enabled"] or []
        wa_linked = bool(r["whatsapp_number"])
        tg_linked = bool(r["telegram_chat_id"]) or (
            bool(channels_enabled) and "telegram" in channels_enabled
        )
        channels[name] = {
            "whatsapp": {
                "linked": wa_linked,
                "identifier": _mask_identifier(r["whatsapp_number"] or ""),
            },
            "telegram": {
                "linked": tg_linked,
                "identifier": "Telegram" if r["telegram_chat_id"] else "",
            },
        }
    return channels


@app.get("/dashboard/task/{task_id}")
async def dashboard_task_detail(task_id: str) -> dict:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.id, t.title, t.due_at, t.priority, t.status,
                   t.planning_state, t.labels, t.is_template, t.template_id,
                   t.task_duration_min, t.earliest_start, t.latest_end,
                   t.hard_deadline, t.soft_deadline, t.created_at,
                   u_assign.name as assignee, u_creator.name as created_by
            FROM tasks t
            LEFT JOIN users u_assign ON t.assignee_id = u_assign.id
            LEFT JOIN users u_creator ON t.created_by = u_creator.id
            WHERE t.id = $1::uuid
            """,
            task_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")

        notes = await conn.fetch(
            """
            SELECT tn.id, tn.content, tn.created_at, u.name as author
            FROM task_notes tn
            LEFT JOIN users u ON tn.author_id = u.id
            WHERE tn.task_id = $1::uuid
            ORDER BY tn.created_at ASC
            """,
            task_id,
        )

        blockers = await conn.fetch(
            """
            SELECT t.id, t.title FROM task_dependencies td
            JOIN tasks t ON t.id = td.parent_id
            WHERE td.child_id = $1::uuid AND t.status = 'active'
            """,
            task_id,
        )

        dependents = await conn.fetch(
            """
            SELECT t.id, t.title FROM task_dependencies td
            JOIN tasks t ON t.id = td.child_id
            WHERE td.parent_id = $1::uuid AND t.status = 'active'
            """,
            task_id,
        )

        template_name = None
        if row["template_id"]:
            trow = await conn.fetchval(
                "SELECT title FROM tasks WHERE id = $1::uuid",
                row["template_id"],
            )
            if trow:
                template_name = trow

    due_iso = row["due_at"].isoformat() if row["due_at"] else None
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "due_at": due_iso,
        "priority": row["priority"] or "medium",
        "status": row["status"],
        "assignee": row["assignee"] or "unassigned",
        "created_by": row["created_by"] or "",
        "labels": row["labels"] or [],
        "is_template": row["is_template"] or False,
        "template_id": str(row["template_id"]) if row["template_id"] else None,
        "template_title": template_name,
        "planning_state": row["planning_state"],
        "task_duration_min": row["task_duration_min"],
        "earliest_start": row["earliest_start"].isoformat() if row["earliest_start"] else None,
        "latest_end": row["latest_end"].isoformat() if row["latest_end"] else None,
        "hard_deadline": row["hard_deadline"].isoformat() if row["hard_deadline"] else None,
        "soft_deadline": row["soft_deadline"].isoformat() if row["soft_deadline"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "notes": [
            {
                "id": str(n["id"]),
                "content": n["content"],
                "author": n["author"] or "",
                "created_at": n["created_at"].isoformat() if n["created_at"] else None,
            }
            for n in notes
        ],
        "blockers": [{"id": str(b["id"]), "title": b["title"]} for b in blockers],
        "dependents": [{"id": str(d["id"]), "title": d["title"]} for d in dependents],
    }


@app.get("/admin")
async def admin_redirect():
    """Redirect the bare /admin URL to the static admin page (D-05)."""
    return RedirectResponse(url="/static/admin.html")


@app.get("/admin/stream")
async def admin_stream():
    """Unauthenticated SSE stream of the admin status payload (D-08, D-10).

    Emits a named `event: status` SSE event with a JSON payload of shape
    `{"services": {...5 entries...}, "channels": {Ruben, Meral},
      "models": {"pulling": [...]}}` every 5 s (during active pulls) or
    45 s (steady state).  No auth challenge is enforced — LAN trust only
    (D-08).
    """

    async def event_generator():
        while True:
            try:
                payload = await _collect_admin_status()
                yield f"event: status\ndata: {json.dumps(payload)}\n\n"
            except Exception as e:
                # Lazy %s logging per CLAUDE.md §Logging.
                log.warning("admin SSE generator error: %s", e)
            # Sleep is OUTSIDE the try so cancellation (client disconnect)
            # can interrupt the wait — required by FastAPI cancellation
            # semantics (T-40-07).
            # Phase 41: 5s cadence during active model pulls, 45s otherwise
            active_pulls = await admin_models.get_all_pull_tasks()
            has_active = any(
                t.status in ("pending", "downloading", "extracting")
                for t in active_pulls
            )
            await asyncio.sleep(5 if has_active else 45)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Admin model management — Phase 41 (LAN trust, no auth per D-08)
# ---------------------------------------------------------------------------


@app.get("/admin/model/list")
async def admin_model_list():
    """List all locally available models and active pull tasks.

    Returns ``{"local": [...], "pulling": [...]}``.  Pull tasks are
    extracted from the module-level tracker used by the SSE generator.
    """
    try:
        local = await admin_models.list_models()
        pulling_tasks = await admin_models.get_all_pull_tasks()
        pulling = [
            {"name": t.model, "status": t.status, "progress": t.progress, "message": t.message}
            for t in pulling_tasks
        ]
        return {"local": local, "pulling": pulling}
    except Exception:
        log.warning("admin_model_list failed, returning empty")
        return {"local": [], "pulling": []}


@app.post("/admin/model/switch")
async def admin_model_switch(req: ModelSwitchRequest):
    """Switch the active Ollama model (persistent across restarts).

    1. Validate model name (regex)
    2. Validate model exists locally via ``admin_models.list_models()``
    3. Persist to ``app_config`` via ``set_active_model()``
    4. Unload old model (fire-and-forget ``keep_alive=0``)
    5. Set loading flag, load new model (blocking, up to 180s)
    6. Roll back on failure
    """
    if not validate_model_name(req.model):
        raise HTTPException(status_code=400, detail="Invalid model name")

    local = await admin_models.list_models()
    if not any(m.get("name") == req.model for m in local):
        raise HTTPException(status_code=404, detail=f"Model '{req.model}' not found locally")

    old_model = get_active_model_sync()

    # Persist the new model
    await set_active_model(req.model)

    # Unload old model (fire-and-forget to free VRAM)
    if old_model and old_model != req.model:
        asyncio.create_task(admin_models.load_model(old_model, keep_alive="0"))

    # Set loading flag for frontend modal (D-05)
    admin_models.set_loading_model(req.model)

    # Load new model — blocking up to 180s for VRAM loading
    success = await admin_models.load_model(req.model)
    if not success:
        # Revert on failure
        await set_active_model(old_model)
        admin_models.set_loading_model(None)
        raise HTTPException(status_code=502, detail=f"Failed to load model '{req.model}'")

    return {"status": "switched", "model": req.model}


@app.post("/admin/model/pull")
async def admin_model_pull(req: ModelPullRequest):
    """Start a background model pull from the Ollama registry.

    Validates the model name, checks for concurrent pulls, then launches
    ``admin_models.pull_model()`` as a background task.  Progress is
    tracked in the module-level ``_pull_tasks`` dict and pushed to the
    frontend via SSE.
    """
    if not validate_model_name(req.model):
        raise HTTPException(status_code=400, detail="Invalid model name")

    # Check concurrent pull (per-model)
    existing = await admin_models.get_pull_status(req.model)
    if existing and existing.status in ("pending", "downloading", "extracting"):
        raise HTTPException(status_code=409, detail="A pull is already in progress for this model")

    # Check concurrent pull (global — one active pull at a time)
    all_tasks = await admin_models.get_all_pull_tasks()
    if any(t.status in ("pending", "downloading", "extracting") for t in all_tasks):
        raise HTTPException(status_code=409, detail="A pull is already in progress")

    # Start background task
    asyncio.create_task(admin_models.pull_model(req.model))

    return {"status": "started", "model": req.model}


@app.post("/admin/model/delete")
async def admin_model_delete(req: ModelDeleteRequest):
    """Delete a model from the local Ollama registry.

    Blocks deletion of the currently active model (backend enforcement
    per D-14 — frontend also disables the button but backend MUST check).
    """
    if not validate_model_name(req.model):
        raise HTTPException(status_code=400, detail="Invalid model name")

    # Block active model deletion (backend enforcement — D-14)
    if req.model == get_active_model_sync():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the active model. Switch to another model first.",
        )

    result = await admin_models.delete_model(req.model)
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("detail", "Model not found"))

    return {"status": "deleted", "model": req.model}


@app.post("/dashboard/chat")
async def dashboard_chat(req: DashboardChatRequest) -> dict:
    """Send a message to Nova from the dashboard and return the reply.

    Accepts { user, message }, runs the full agent loop, and returns
    { reply }. Empty messages return 400. Agent loop failures return 502.
    """
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        reply = await run_agent(
            req.message.strip(),
            user=req.user,
            history=None,
            channel="dashboard",
        )
    except Exception as e:
        log.error("Dashboard chat agent loop failed for %s: %s", req.user, e)
        raise HTTPException(
            status_code=502,
            detail="Nova is having trouble right now. Please try again later.",
        )

    return {"reply": reply}


@app.post("/dashboard/link-whatsapp/start")
async def link_whatsapp_start(req: LinkWhatsAppStartRequest):
    """Start WhatsApp OTP linking flow — validate number, check conflicts/rate limits, send code."""
    import secrets
    from datetime import datetime, timezone, timedelta

    pool = await db.get_pool()

    # 1. Validate user exists
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

    # 2. Clean and validate number
    clean_number = req.number.strip().lstrip("+")
    if not clean_number.isdigit() or len(clean_number) < 8:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    async with pool.acquire() as conn:
        # 3. Check number uniqueness (claim conflict)
        existing_owner = await conn.fetchval(
            """
            SELECT u.name FROM user_preferences up
            JOIN users u ON up.user_id = u.id
            WHERE up.whatsapp_number = $1 AND u.name != $2
            """,
            clean_number,
            req.user,
        )
        if existing_owner:
            raise HTTPException(
                status_code=400,
                detail=f"This number is already linked to {existing_owner}",
            )

        # 4. Check rate limit (1 code per number per 5 minutes)
        rate_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM channel_verification_codes
            WHERE whatsapp_number = $1 AND created_at > now() - interval '5 minutes'
            """,
            clean_number,
        )
        if rate_count and rate_count > 0:
            raise HTTPException(
                status_code=429,
                detail="A code was already sent recently. Please wait 5 minutes before requesting a new code.",
            )

        # 5. Generate code
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # 6. Insert verification code
        await conn.execute(
            """
            INSERT INTO channel_verification_codes (user_id, whatsapp_number, code, expires_at, channel)
            VALUES ($1, $2, $3, $4, 'whatsapp')
            """,
            user_id,
            clean_number,
            code,
            expires_at,
        )

    # 7. Send OTP via WhatsApp
    try:
        await send_whatsapp_otp(clean_number, code)
    except RuntimeError:
        raise HTTPException(
            status_code=502,
            detail="Failed to send verification code. Please try again.",
        )

    # 8. Log that a code was sent (never log the code itself)
    log.info("Verification code sent to user %s via WhatsApp", req.user)

    return {"status": "code_sent"}


@app.post("/dashboard/link-whatsapp/verify")
async def link_whatsapp_verify(req: LinkWhatsAppVerifyRequest):
    """Verify the OTP code entered by the user and link the WhatsApp number."""
    from datetime import datetime, timezone

    pool = await db.get_pool()

    # 1. Look up user
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Fetch most recent active code
        row = await conn.fetchrow(
            """
            SELECT id, whatsapp_number, code, attempts, expires_at
            FROM channel_verification_codes
            WHERE user_id = $1 AND channel = 'whatsapp' AND attempts < 3 AND expires_at > now()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
        )
        if not row:
            raise HTTPException(
                status_code=400,
                detail="No active verification code found. Please request a new code.",
            )

        # 3. Increment attempts immediately (always counts toward limit)
        await conn.execute(
            "UPDATE channel_verification_codes SET attempts = attempts + 1 WHERE id = $1",
            row["id"],
        )

        # 4. Compare code
        remaining = 2 - row["attempts"]  # attempts left after THIS one
        if row["code"] != req.code.strip():
            if remaining <= 0:
                # Expire code immediately
                await conn.execute(
                    "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
                    row["id"],
                )
                raise HTTPException(
                    status_code=400,
                    detail="Incorrect code. No attempts remaining. Please request a new code.",
                )
            raise HTTPException(
                status_code=400,
                detail=f"Incorrect code. {remaining} attempts remaining.",
            )

        # 5. Correct code — link the number
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, whatsapp_number)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET whatsapp_number = EXCLUDED.whatsapp_number
            """,
            user_id,
            row["whatsapp_number"],
        )

        # 6. Mark code as consumed
        await conn.execute(
            "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
            row["id"],
        )

    return {"status": "success", "linked_number": row["whatsapp_number"]}


@app.post("/dashboard/link-telegram/start")
async def link_telegram_start(req: LinkTelegramStartRequest):
    """Start Telegram OTP linking flow — validate user, check chat_id, rate limits, send code."""
    import secrets
    from datetime import datetime, timezone, timedelta

    pool = await db.get_pool()

    # 1. Validate user exists
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Look up Telegram chat_id
        chat_id = await conn.fetchval(
            """
            SELECT ci.channel_id FROM channel_identities ci
            JOIN users u ON ci.user_id = u.id
            WHERE u.name = $1 AND ci.channel = 'telegram'
            """,
            req.user,
        )
        if not chat_id:
            raise HTTPException(
                status_code=400,
                detail="No Telegram account linked to this user. Please send a message to Nova on Telegram first.",
            )

        # 3. Check rate limit (1 code per user per 5 minutes for telegram)
        rate_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM channel_verification_codes
            WHERE user_id = $1 AND channel = 'telegram' AND created_at > now() - interval '5 minutes'
            """,
            user_id,
        )
        if rate_count and rate_count > 0:
            raise HTTPException(
                status_code=429,
                detail="A code was already sent recently. Please wait 5 minutes before requesting a new code.",
            )

        # 4. Generate 6-digit code
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # 5. Insert verification code (store chat_id in whatsapp_number column)
        await conn.execute(
            """
            INSERT INTO channel_verification_codes (user_id, whatsapp_number, code, expires_at, channel)
            VALUES ($1, $2, $3, $4, 'telegram')
            """,
            user_id,
            chat_id,
            code,
            expires_at,
        )

    # 6. Send OTP via Telegram DM
    try:
        sent = await send_telegram_otp(req.user, code)
        if not sent:
            raise RuntimeError("No chat_id found")
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Failed to send verification code via Telegram. Please try again.",
        )

    # 7. Log that a code was sent (never log the code itself)
    log.info("Verification code sent to user %s via Telegram", req.user)

    return {"status": "code_sent"}


@app.post("/dashboard/link-telegram/verify")
async def link_telegram_verify(req: LinkTelegramVerifyRequest):
    """Verify the OTP code entered by the user and enable Telegram channel."""
    from datetime import datetime, timezone

    pool = await db.get_pool()

    # 1. Look up user
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Fetch most recent active code for telegram
        row = await conn.fetchrow(
            """
            SELECT id, whatsapp_number, code, attempts, expires_at
            FROM channel_verification_codes
            WHERE user_id = $1 AND channel = 'telegram' AND attempts < 3 AND expires_at > now()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
        )
        if not row:
            raise HTTPException(
                status_code=400,
                detail="No active verification code found. Please request a new code.",
            )

        # 3. Increment attempts immediately (always counts toward limit)
        await conn.execute(
            "UPDATE channel_verification_codes SET attempts = attempts + 1 WHERE id = $1",
            row["id"],
        )

        # 4. Compare code
        remaining = 2 - row["attempts"]  # attempts left after THIS one
        if row["code"] != req.code.strip():
            if remaining <= 0:
                # Expire code immediately
                await conn.execute(
                    "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
                    row["id"],
                )
                raise HTTPException(
                    status_code=400,
                    detail="Incorrect code. No attempts remaining. Please request a new code.",
                )
            raise HTTPException(
                status_code=400,
                detail=f"Incorrect code. {remaining} attempts remaining.",
            )

        # 5. Correct code — enable telegram in channels_enabled (idempotent)
        await conn.execute(
            """
            UPDATE user_preferences
            SET channels_enabled = ARRAY_APPEND(
                COALESCE(channels_enabled, '{}'),
                'telegram'
            )
            WHERE user_id = $1 AND NOT ('telegram' = ANY(COALESCE(channels_enabled, '{}')))
            """,
            user_id,
        )

        # 5.5. Record channel identity (idempotent — handles re-linking)
        await conn.execute(
            """INSERT INTO channel_identities (user_id, channel, channel_id)
               VALUES ($1, 'telegram', $2)
               ON CONFLICT (channel, channel_id) DO UPDATE SET user_id = EXCLUDED.user_id""",
            user_id, row["whatsapp_number"],
        )

        # 6. Mark code as consumed
        await conn.execute(
            "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
            row["id"],
        )

    return {"status": "success"}


@app.get("/webhooks/whatsapp")
async def whatsapp_handshake(
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge"),
):
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    
    if not verify_whatsapp_signature(body, signature, settings.whatsapp_app_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    try:
        import json
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
        
    background_tasks.add_task(process_incoming_whatsapp, payload)
    return {"status": "accepted"}


@app.get("/api/preferences")
async def get_preferences():
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
    prefs = {}
    for r in rows:
        prefs[r["name"]] = {
            "whatsapp_number": r["whatsapp_number"] or "",
            "dnd_enabled": r["dnd_enabled"] if r["dnd_enabled"] is not None else False,
            "dnd_start": r["dnd_start"].strftime("%H:%M") if r["dnd_start"] else "22:00",
            "dnd_end": r["dnd_end"].strftime("%H:%M") if r["dnd_end"] else "07:00",
            "morning_enabled": r["morning_briefing_enabled"] if r["morning_briefing_enabled"] is not None else True,
            "morning_time": r["morning_briefing_time"].strftime("%H:%M") if r["morning_briefing_time"] else "07:00",
            "weekly_enabled": r["weekly_briefing_enabled"] if r["weekly_briefing_enabled"] is not None else True,
            "weekly_day": r["weekly_briefing_day"] if r["weekly_briefing_day"] is not None else 1,
            "weekly_time": r["weekly_briefing_time"].strftime("%H:%M") if r["weekly_briefing_time"] else "09:00",
            "channels_enabled": r["channels_enabled"] if r["channels_enabled"] is not None else [],
        }
    return prefs


@app.post("/api/preferences/request-code")
async def request_code(req: RequestCodeRequest):
    import secrets
    from datetime import datetime, timezone, timedelta
    from .channels.whatsapp import send_whatsapp_message
    
    clean_number = req.number.strip().lstrip("+")
    if not clean_number.isdigit() or len(clean_number) < 8:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    pool = await db.get_pool()

    if req.channel == "telegram":
        if not req.channel_id or not req.channel_id.strip():
            raise HTTPException(status_code=400, detail="channel_id is required for Telegram linking")
        async with pool.acquire() as conn:
            existing_owner = await conn.fetchval(
                """
                SELECT u.name FROM channel_identities ci
                JOIN users u ON ci.user_id = u.id
                WHERE ci.channel = 'telegram' AND ci.channel_id = $1 AND u.name != $2
                """,
                req.channel_id.strip(),
                req.user
            )
            if existing_owner:
                raise HTTPException(
                    status_code=400,
                    detail=f"This Telegram account is already linked to {existing_owner}"
                )
    else:
        async with pool.acquire() as conn:
            existing_owner = await conn.fetchval(
                """
                SELECT u.name 
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                WHERE up.whatsapp_number = $1 AND u.name != $2
                """,
                clean_number,
                req.user
            )
            if existing_owner:
                raise HTTPException(
                    status_code=400,
                    detail=f"This number is already linked to {existing_owner}"
                )

    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
            
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        channel_id_val = req.channel_id.strip() if req.channel == "telegram" and req.channel_id else ""
        
        await conn.execute(
            """
            INSERT INTO channel_verification_codes (user_id, whatsapp_number, code, expires_at, channel, channel_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            clean_number,
            code,
            expires_at,
            req.channel,
            channel_id_val
        )

    otp_message = f"Your Nova verification code is {code}. It expires in 10 minutes."
    if req.channel == "telegram":
        try:
            sent = await send_telegram_otp(req.user, code)
            if not sent:
                raise RuntimeError("No chat_id found")
        except Exception as e:
            log.error("Failed to send Telegram OTP to %s: %s", req.user, e)
            raise HTTPException(
                status_code=502,
                detail="Failed to send verification code via Telegram. Please try again."
            )
    else:
        try:
            await send_whatsapp_message(clean_number, otp_message)
        except Exception as e:
            log.error("Failed to send OTP to %s: %s", clean_number, e)

    # Never log the code itself — only metadata about which user/channel received it
    log.info("Verification code sent to user %s via %s", req.user, req.channel)
    return {"status": "code_sent"}


@app.post("/api/preferences/verify-code")
async def verify_code(req: VerifyCodeRequest):
    from datetime import datetime, timezone
    
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
            
        row = await conn.fetchrow(
            """
            SELECT id, whatsapp_number, code, attempts, expires_at, channel, channel_id
            FROM channel_verification_codes
            WHERE user_id = $1 AND attempts < 3 AND expires_at > now()
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id
        )
        if not row:
            raise HTTPException(status_code=400, detail="No active or valid verification code found")
            
        attempts = row["attempts"]
        if attempts >= 3:
            raise HTTPException(status_code=400, detail="Verification code has been blocked due to too many attempts")
            
        await conn.execute(
            "UPDATE channel_verification_codes SET attempts = attempts + 1 WHERE id = $1",
            row["id"]
        )
        
        if row["code"] != req.code.strip():
            raise HTTPException(status_code=400, detail="Incorrect verification code")
            
        if row["channel"] == "telegram":
            channel_id_val = row["channel_id"]
            if channel_id_val:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO channel_identities (user_id, channel, channel_id)
                        VALUES ($1, 'telegram', $2)
                        ON CONFLICT (channel, channel_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
                        """,
                        user_id,
                        str(channel_id_val)
                    )
                    await conn.execute(
                        """
                        UPDATE user_preferences SET channels_enabled = ARRAY_APPEND(
                            COALESCE(channels_enabled, '{}'),
                            'telegram'
                        ) WHERE user_id = $1 AND NOT ('telegram' = ANY(COALESCE(channels_enabled, '{}')))
                        """,
                        user_id
                    )
                    await conn.execute(
                        "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
                        row["id"]
                    )
        else:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO user_preferences (user_id, whatsapp_number)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO UPDATE SET whatsapp_number = EXCLUDED.whatsapp_number
                    """,
                    user_id,
                    row["whatsapp_number"]
                )
                await conn.execute(
                    """
                    INSERT INTO channel_identities (user_id, channel, channel_id)
                    VALUES ($1, 'whatsapp', $2)
                    ON CONFLICT (channel, channel_id) DO UPDATE SET channel_id = EXCLUDED.channel_id
                    """,
                    user_id,
                    row["whatsapp_number"]
                )
                await conn.execute(
                    "UPDATE channel_verification_codes SET attempts = 99 WHERE id = $1",
                    row["id"]
                )
        
    return {"status": "success", "linked_number": row["whatsapp_number"]}


@app.post("/api/preferences/briefings")
async def save_briefing_preferences(req: BriefingSettingsRequest):
    # Parse times
    try:
        from datetime import datetime
        m_time = datetime.strptime(req.morning_time, "%H:%M").time()
        w_time = datetime.strptime(req.weekly_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Must be HH:MM.")
        
    if req.weekly_day < 1 or req.weekly_day > 7:
        raise HTTPException(status_code=400, detail="Invalid day of week. Must be 1-7 (Monday-Sunday).")
        
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
            
        await conn.execute(
            """
            INSERT INTO user_preferences (
                user_id, 
                morning_briefing_enabled, morning_briefing_time,
                weekly_briefing_enabled, weekly_briefing_day, weekly_briefing_time
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id) DO UPDATE SET
                morning_briefing_enabled = EXCLUDED.morning_briefing_enabled,
                morning_briefing_time = EXCLUDED.morning_briefing_time,
                weekly_briefing_enabled = EXCLUDED.weekly_briefing_enabled,
                weekly_briefing_day = EXCLUDED.weekly_briefing_day,
                weekly_briefing_time = EXCLUDED.weekly_briefing_time
            """,
            user_id,
            req.morning_enabled,
            m_time,
            req.weekly_enabled,
            req.weekly_day,
            w_time
        )
        
    return {"status": "success"}


@app.post("/api/preferences/dnd")
async def save_dnd_preferences(req: DNDSettingsRequest):
    try:
        from datetime import datetime
        d_start = datetime.strptime(req.dnd_start, "%H:%M").time()
        d_end = datetime.strptime(req.dnd_end, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid time format. Must be HH:MM.")
        
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE name = $1", req.user)
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
            
        await conn.execute(
            """
            INSERT INTO user_preferences (user_id, dnd_enabled, dnd_start, dnd_end)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET
                dnd_enabled = EXCLUDED.dnd_enabled,
                dnd_start = EXCLUDED.dnd_start,
                dnd_end = EXCLUDED.dnd_end
            """,
            user_id,
            req.dnd_enabled,
            d_start,
            d_end
        )
        
    return {"status": "success"}


static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


