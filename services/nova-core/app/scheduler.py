"""Background scheduler jobs module."""
from __future__ import annotations

from datetime import datetime, time, timezone, timedelta
import zoneinfo

from .config import settings
from .db import get_pool, get_user_memories
from . import maintenance
from .channels.whatsapp import send_whatsapp_message
from .channels.dispatcher import send_to_user
from .tools.calendar import _get_calendar
from .tools.email import fetch_emails_from_graph, classify_importance


async def send_morning_briefing_for_user(user_name: str):
    """Send personalized morning briefing to a specific user."""
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    start_of_today = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_of_today = datetime.combine(now_local.date(), time.max, tzinfo=tz)
    
    pool = await get_pool()
    
    emails = await fetch_emails_from_graph(limit=10)
    important_mails = []
    for mail in emails:
        if await classify_importance(mail["subject"], mail["from"], mail["preview"]):
            important_mails.append(mail)
            
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow("SELECT id FROM users WHERE name = $1", user_name)
        if user_row:
            tasks = await conn.fetch(
                """
                SELECT title, due_at FROM tasks 
                WHERE status = 'active' AND assignee_id = $1
                ORDER BY due_at ASC NULLS LAST
                """,
                user_row["id"]
            )
        else:
            tasks = []
            
    calendar = _get_calendar()
    events = calendar.search(start=start_of_today, end=end_of_today, event=True, expand=True)
    
    briefing = f"Good morning, {user_name}! Here is your briefing for today.\n\n"
    
    briefing += "*Your Active Tasks:*\n"
    if tasks:
        for t in tasks:
            due_str = f" (due {t['due_at'].strftime('%H:%M')})" if t["due_at"] else ""
            briefing += f"- {t['title']}{due_str}\n"
    else:
        briefing += "- No tasks assigned.\n"
    briefing += "\n"
    
    briefing += "*Today's Calendar:*\n"
    if events:
        for ev in events:
            vevent = ev.vobject_instance.vevent
            summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
            dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            time_str = dtstart.strftime('%H:%M') if isinstance(dtstart, datetime) else "All Day"
            briefing += f"- {summary} ({time_str})\n"
    else:
        briefing += "- No events today.\n"
    briefing += "\n"
    
    briefing += "*Important Emails:*\n"
    if important_mails:
        for mail in important_mails[:3]:
            briefing += f"- From: {mail['from']}\n  Subject: {mail['subject']}\n"
    else:
        briefing += "- No new important emails.\n"
        
    # Per D-04: Include per-user memories (private + household)
    user_memories = await get_user_memories(user_name)
    if user_memories:
        briefing += "\n*Nova remembers:*\n"
        briefing += user_memories + "\n"
        
    await send_to_user(user_name, briefing, proactive=True)


async def send_weekly_briefing_for_user(user_name: str):
    """Send personalized 7-day outlook weekly briefing to a specific user."""
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    start_of_today = datetime.combine(now_local.date(), time.min, tzinfo=tz)
    end_of_week = start_of_today + timedelta(days=7)
    
    pool = await get_pool()
    
    emails = await fetch_emails_from_graph(limit=10)
    important_mails = []
    for mail in emails:
        if await classify_importance(mail["subject"], mail["from"], mail["preview"]):
            important_mails.append(mail)
            
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow("SELECT id FROM users WHERE name = $1", user_name)
        if user_row:
            tasks = await conn.fetch(
                """
                SELECT title, due_at FROM tasks 
                WHERE status = 'active' AND assignee_id = $1
                ORDER BY due_at ASC NULLS LAST
                """,
                user_row["id"]
            )
        else:
            tasks = []
            
    calendar = _get_calendar()
    events = calendar.search(start=start_of_today, end=end_of_week, event=True, expand=True)
    
    briefing = f"Good morning, {user_name}! Here is your weekly briefing.\n\n"
    
    briefing += "*Your Active Tasks:*\n"
    if tasks:
        for t in tasks:
            due_str = f" (due {t['due_at'].strftime('%Y-%m-%d %H:%M')})" if t["due_at"] else ""
            briefing += f"- {t['title']}{due_str}\n"
    else:
        briefing += "- No tasks assigned.\n"
    briefing += "\n"
    
    briefing += "*Upcoming Events (7 Days):*\n"
    if events:
        for ev in events:
            vevent = ev.vobject_instance.vevent
            summary = vevent.summary.value if hasattr(vevent, "summary") else "No Title"
            dtstart = vevent.dtstart.value if hasattr(vevent, "dtstart") else None
            time_str = dtstart.strftime('%a, %d %b %H:%M') if isinstance(dtstart, datetime) else "All Day"
            briefing += f"- {summary} ({time_str})\n"
    else:
        briefing += "- No upcoming events.\n"
    briefing += "\n"
    
    briefing += "*Recent Important Emails:*\n"
    if important_mails:
        for mail in important_mails[:3]:
            briefing += f"- From: {mail['from']}\n  Subject: {mail['subject']}\n"
    else:
        briefing += "- No new important emails.\n"
        
    # Per D-04: Include per-user memories (private + household)
    user_memories = await get_user_memories(user_name)
    if user_memories:
        briefing += "\n*Nova remembers:*\n"
        briefing += user_memories + "\n"
        
    await send_to_user(user_name, briefing, proactive=True)


async def send_morning_briefing():
    """Daily morning briefing summarizing tasks, calendar events, and important emails (legacy/fallback)."""
    from . import identity
    users_map = await identity.get_all_whatsapp_users()
    for number, user in users_map.items():
        await send_morning_briefing_for_user(user.name)


async def run_briefing_scheduler():
    """Runs every minute to check if any user is due for their morning or weekly briefing."""
    import zoneinfo
    
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_local = datetime.now(tz)
    current_time = now_local.time()
    current_day = now_local.weekday() + 1  # 1 = Monday, ..., 7 = Sunday
    
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.name,
                       up.morning_briefing_enabled, up.morning_briefing_time,
                       up.weekly_briefing_enabled, up.weekly_briefing_day, up.weekly_briefing_time
                FROM user_preferences up
                JOIN users u ON up.user_id = u.id
                """
            )
            for r in rows:
                name = r["name"]
                
                if r["morning_briefing_enabled"] and r["morning_briefing_time"]:
                    m_time = r["morning_briefing_time"]
                    if m_time.hour == current_time.hour and m_time.minute == current_time.minute:
                        await send_morning_briefing_for_user(name)
                        
                if r["weekly_briefing_enabled"] and r["weekly_briefing_day"] and r["weekly_briefing_time"]:
                    w_day = r["weekly_briefing_day"]
                    w_time = r["weekly_briefing_time"]
                    if w_day == current_day and w_time.hour == current_time.hour and w_time.minute == current_time.minute:
                        await send_weekly_briefing_for_user(name)
    except Exception as e:
        print(f"[ERROR] Briefing scheduler error: {e}")


async def check_overdue_tasks():
    """Hourly check for tasks that are past their due dates."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        overdue_tasks = await conn.fetch(
            """
            SELECT t.title, t.due_at, u.name as assignee, u.id as user_id
            FROM tasks t
            LEFT JOIN users u ON t.assignee_id = u.id
            WHERE t.status = 'active' AND t.due_at < now()
            """
        )
        
    if not overdue_tasks:
        return
        
    for task in overdue_tasks:
        assignee_name = task["assignee"]
        if assignee_name:
            due_str = task["due_at"].strftime('%Y-%m-%d %H:%M')
            alert = f"Reminder: Your task '{task['title']}' was due at {due_str}."
            await send_to_user(assignee_name, alert, proactive=True)


async def check_new_emails():
    """Triage recent emails and push notifications for new important ones."""
    emails = await fetch_emails_from_graph(limit=10)
    if not emails:
        return
        
    pool = await get_pool()
    for mail in emails:
        # Check if email is important
        is_important = await classify_importance(mail["subject"], mail["from"], mail["preview"])
        if not is_important:
            continue
            
        # Check database if already processed
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM processed_emails WHERE email_id = $1",
                mail["id"]
            )
            if exists:
                continue
                
            # Log as processed
            await conn.execute(
                "INSERT INTO processed_emails (email_id) VALUES ($1) ON CONFLICT DO NOTHING",
                mail["id"]
            )
            
        alert = (
            f"New Important Email\n"
            f"From: {mail['from']}\n"
            f"Subject: {mail['subject']}\n"
            f"Preview: {mail['preview']}"
        )
        pool = await get_pool()
        async with pool.acquire() as conn:
            user_rows = await conn.fetch(
                "SELECT u.name FROM user_preferences up JOIN users u ON up.user_id = u.id"
            )
            for row in user_rows:
                await send_to_user(row["name"], alert, proactive=True)


async def process_queued_notifications():
    """Runs every minute to flush queued notifications for users whose DND window has ended."""
    from .db import get_pool, get_user_memories
    from .identity import is_user_in_dnd
    
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            queued = await conn.fetch(
                """
                SELECT q.id, q.whatsapp_number, q.message_text, q.channel, u.name
                FROM queued_notifications q
                JOIN users u ON q.user_id = u.id
                ORDER BY q.created_at ASC
                """
            )
            for row in queued:
                name = row["name"]
                msg_text = row["message_text"]
                channel = row["channel"] or "whatsapp"
                
                in_dnd = await is_user_in_dnd(name)
                if not in_dnd:
                    if channel == "telegram":
                        from .channels.telegram import adapter as telegram_adapter
                        await telegram_adapter.send_message(name, msg_text, proactive=False)
                    else:
                        number = row["whatsapp_number"]
                        if number:
                            await send_whatsapp_message(number, msg_text, proactive=False)
                    await conn.execute("DELETE FROM queued_notifications WHERE id = $1", row["id"])
    except Exception as e:
        print(f"[ERROR] Error processing queued notifications: {e}")


# ------------------------------------------------------------------
# Scheduled Maintenance Agent (Phase 29)
# ------------------------------------------------------------------


async def run_maintenance_dep_scan():
    """Nightly dependency/CVE check."""
    if not settings.maintenance_dep_check_enabled:
        return
    await maintenance.dependency_scanner.run_dependency_scan()


async def run_maintenance_log_anomaly():
    """Nightly log-anomaly review."""
    if not settings.maintenance_log_anomaly_enabled:
        return
    await maintenance.log_anomaly.run_log_anomaly_review()


async def run_maintenance_backup_verify():
    """Nightly backup verification."""
    if not settings.maintenance_backup_verify_enabled:
        return
    await maintenance.backup_verifier.run_backup_verification()


async def run_maintenance_trend_report():
    """Weekly disk/VRAM trend report."""
    if not settings.maintenance_trend_report_enabled:
        return
    await maintenance.trend_reporter.run_trend_report()
