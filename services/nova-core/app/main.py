"""Nova Core — FastAPI entrypoint.

Exposes:
  GET  /health                     liveness + Ollama readiness
  POST /v1/chat/completions        OpenAI-compatible agent endpoint (all channels)
  GET  /dashboard/tasks            read-only feed for the Phase 8 dashboard (stub)
  GET  /dashboard/events           read-only feed for the Phase 8 dashboard (stub)

Channel webhooks (WhatsApp, Phase 4) will be added under /webhooks/*.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import zoneinfo

from fastapi import FastAPI, Request, Query, BackgroundTasks, Response, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import llm, db
from .agent import run_agent
from .config import settings
from .models import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice, RequestCodeRequest, VerifyCodeRequest, BriefingSettingsRequest, DNDSettingsRequest, LinkWhatsAppStartRequest, LinkWhatsAppVerifyRequest
from .security import verify_whatsapp_signature, verify_telegram_signature
from .channels.whatsapp import process_incoming_whatsapp, send_whatsapp_otp
from .channels.telegram import process_incoming_telegram
from .db import get_pool as db_get_pool
from .tools.calendar import _get_calendar

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .scheduler import check_new_emails, send_morning_briefing, check_overdue_tasks, run_briefing_scheduler, process_queued_notifications

log = logging.getLogger("nova-core")

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool and run migrations
    await db.get_pool()
    await db.run_migrations()
    
    # Register background jobs
    scheduler.add_job(check_new_emails, "interval", minutes=5, id="check_new_emails")
    scheduler.add_job(run_briefing_scheduler, "interval", minutes=1, id="run_briefing_scheduler")
    scheduler.add_job(process_queued_notifications, "interval", minutes=1, id="process_queued_notifications")
    scheduler.add_job(check_overdue_tasks, "interval", hours=1, id="check_overdue_tasks")
    scheduler.start()

    # Register Telegram bot command menu if enabled
    if settings.telegram_enabled and settings.telegram_bot_token:
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
                    log.warning(f"Telegram command registration failed: {resp.status_code}")
        except Exception as e:
            log.warning(f"Telegram command registration error: {e}")
    
    yield
    # Shutdown scheduler and close database pool
    scheduler.shutdown()
    await db.close_pool()


app = FastAPI(title="Nova Core", version="0.1.0", lifespan=lifespan)



@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama_ready": await llm.is_ready()}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest, request: Request, user: str | None = None) -> ChatCompletionResponse:
    """Run the agent loop for the latest user message and return the reply."""
    if settings.nova_api_token:
        import hmac
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], settings.nova_api_token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    resolved_user = user or req.user or "household"
    history = [m.model_dump() for m in req.messages[:-1]]
    last = req.messages[-1].content if req.messages else ""

    try:
        reply = await run_agent(last, user=resolved_user, history=history)
    except Exception as e:
        print(f"[ERROR] Agent loop failed: {e}")
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
            SELECT t.title, t.due_at, u.name as assignee
            FROM tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            WHERE t.status = 'active'
            ORDER BY t.due_at ASC NULLS LAST, t.created_at ASC
            """
        )
    tasks = []
    for r in rows:
        due_iso = r["due_at"].isoformat() if r["due_at"] else None
        tasks.append({
            "title": r["title"],
            "due_at": due_iso,
            "assignee": r["assignee"] or "unassigned"
        })
    return {"tasks": tasks}


@app.get("/dashboard/events")
async def dashboard_events() -> dict:
    from datetime import datetime, timezone, timedelta
    import zoneinfo
    from .tools.calendar import _get_calendar
    
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    start_dt = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=tz)
    end_dt = start_dt + timedelta(days=7)
    
    try:
        calendar = _get_calendar()
        events = calendar.search(start=start_dt, end=end_dt, event=True, expand=True)
    except Exception as e:
        print(f"[ERROR] Failed to fetch calendar: {e}")
        return {"events": []}
        
    events_list = []
    for ev in events:
        vevent = ev.vobject_instance.vevent
        summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
        dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
        dtend = vevent.dtend.value if hasattr(vevent, "dtend") else None
        location = vevent.location.value if hasattr(vevent, "location") and vevent.location.value else ""
        events_list.append({
            "title": summary,
            "start": dtstart.isoformat() if dtstart else "",
            "end": dtend.isoformat() if dtend else "",
            "location": location
        })
    return {"events": events_list}


@app.get("/dashboard")
async def dashboard_redirect():
    return RedirectResponse(url="/static/index.html")


@app.get("/dashboard/stream")
async def dashboard_stream():
    import asyncio
    import json
    
    async def event_generator():
        while True:
            try:
                tasks_data = await dashboard_tasks()
                events_data = await dashboard_events()
                payload = {
                    "tasks": tasks_data["tasks"],
                    "events": events_data["events"]
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as e:
                print(f"[ERROR] SSE generator error: {e}")
            await asyncio.sleep(15)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")



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

    # 8. Log code for debugging
    print(f"[OTP STATUS] Verification code for {req.user} ({clean_number}): {code}")

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


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    if not settings.telegram_enabled:
        raise HTTPException(status_code=404, detail="Telegram channel is not enabled")

    body = await request.body()
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

    if not verify_telegram_signature(secret_token, settings.telegram_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid secret token")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    update = payload if isinstance(payload, dict) else {}
    msg = update.get("message", {})
    text = msg.get("text", "")
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))

    if text and chat_id:
        update_id = update.get("update_id")
        if update_id is not None:
            pool = await db_get_pool()
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "INSERT INTO processed_telegram_updates (update_id) VALUES ($1) ON CONFLICT (update_id) DO NOTHING",
                    update_id
                )
                if result != "INSERT 0 1":
                    return {"status": "accepted"}

        if text.startswith("/"):
            from .channels.telegram import send_telegram_message
            reply = _handle_telegram_command(text)
            background_tasks.add_task(send_telegram_message, chat_id, reply)
        else:
            background_tasks.add_task(process_incoming_telegram, payload)

    return {"status": "accepted"}


@app.get("/api/preferences")
async def get_preferences():
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT u.name, up.whatsapp_number, up.dnd_enabled, up.dnd_start, up.dnd_end,
                   up.morning_briefing_enabled, up.morning_briefing_time,
                   up.weekly_briefing_enabled, up.weekly_briefing_day, up.weekly_briefing_time
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
        from .channels.dispatcher import send_to_user
        try:
            await send_to_user(req.user, otp_message, proactive=False)
        except Exception as e:
            print(f"[ERROR] Failed to send Telegram OTP to {req.user}: {e}")
    else:
        try:
            await send_whatsapp_message(clean_number, otp_message)
        except Exception as e:
            print(f"[ERROR] Failed to send OTP to {clean_number}: {e}")

    print(f"[OTP STATUS] Verification code for {req.user} ({clean_number}, {req.channel}): {code}")
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
        else:
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


def _handle_telegram_command(text: str) -> str:
    """Handle Telegram bot commands. Returns the reply text."""
    cmd = text.split()[0].lower()
    if cmd == "/help":
        return (
            "\U0001f916 I'm Nova, your household assistant.\n\n"
            "I can help with:\n"
            "\U0001f4cb Tasks — add, list, complete household tasks\n"
            "\U0001f4c5 Calendar — check your schedule and events\n"
            "\U0001f4e8 Email — get important email notifications\n"
            "\u23f0 Briefings — morning and weekly summaries\n\n"
            "Just ask me anything! For example:\n"
            '• "What\'s on my calendar today?"\n'
            '• "Add milk to the shopping list"\n'
            '• "What tasks are overdue?"\n\n'
            "Commands:\n"
            "/help — Show this message\n"
            "/tasks — Show your current tasks\n"
            "/settings — Manage your preferences"
        )
    elif cmd == "/tasks":
        return "Task management coming soon. Try asking 'What are my tasks?' in the meantime."
    elif cmd == "/settings":
        return "Preferences management coming soon. Use the web dashboard to adjust your settings."
    return f"Unknown command: {cmd}. Try /help."


import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


