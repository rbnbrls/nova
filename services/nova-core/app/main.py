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
from fastapi import FastAPI

from . import llm, db
from .agent import run_agent
from .config import settings
from .models import ChatCompletionRequest, ChatCompletionResponse, ChatMessage, Choice


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the database pool
    await db.get_pool()
    yield
    # Close the database pool
    await db.close_pool()


app = FastAPI(title="Nova Core", version="0.1.0", lifespan=lifespan)



@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ollama_ready": await llm.is_ready()}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest) -> ChatCompletionResponse:
    """Run the agent loop for the latest user message and return the reply."""
    user = req.user or "household"
    history = [m.model_dump() for m in req.messages[:-1]]
    last = req.messages[-1].content if req.messages else ""

    reply = await run_agent(last, user=user, history=history)

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
