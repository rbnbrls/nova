"""Nova Core — FastAPI entrypoint.

Exposes:
  GET  /health                     liveness + Ollama readiness
  POST /v1/chat/completions        OpenAI-compatible agent endpoint (all channels)
  GET  /dashboard/tasks            read-only feed for the Phase 8 dashboard (stub)
  GET  /dashboard/events           read-only feed for the Phase 8 dashboard (stub)

Channel webhooks (WhatsApp, Phase 4) will be added under /webhooks/*.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Query, BackgroundTasks, Response, HTTPException

from . import llm, db
from .agent import run_agent
from .config import settings
from .models import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice
from .security import verify_whatsapp_signature


from .whatsapp import process_incoming_whatsapp




from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .scheduler import check_new_emails, send_morning_briefing, check_overdue_tasks

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool and run migrations
    await db.get_pool()
    await db.run_migrations()
    
    # Register background jobs
    scheduler.add_job(check_new_emails, "interval", minutes=5, id="check_new_emails")
    scheduler.add_job(send_morning_briefing, "cron", hour=7, minute=0, id="send_morning_briefing")
    scheduler.add_job(check_overdue_tasks, "interval", hours=1, id="check_overdue_tasks")
    scheduler.start()
    
    yield
    # Shutdown scheduler and close database pool
    scheduler.shutdown()
    await db.close_pool()


app = FastAPI(title="Nova Core", version="0.1.0", lifespan=lifespan)



@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama_ready": await llm.is_ready()}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest, user: str | None = None) -> ChatCompletionResponse:
    """Run the agent loop for the latest user message and return the reply."""
    resolved_user = user or req.user or "household"
    history = [m.model_dump() for m in req.messages[:-1]]
    last = req.messages[-1].content if req.messages else ""

    reply = await run_agent(last, user=resolved_user, history=history)

    return ChatCompletionResponse(
        model=req.model or settings.nova_model,
        choices=[Choice(message=ChatMessage(role="assistant", content=reply))],
    )


# --- Dashboard feeds (Phase 8; real queries land with Phase 5 data tools) ---


@app.get("/dashboard/tasks")
async def dashboard_tasks() -> dict:
    # TODO(Phase 5/8): SELECT active tasks with due_at, grouped by assignee.
    return {"tasks": []}


@app.get("/dashboard/events")
async def dashboard_events() -> dict:
    # TODO(Phase 5/8): fetch upcoming CalDAV events.
    return {"events": []}


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

