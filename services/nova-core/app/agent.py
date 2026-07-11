"""The Nova agent loop: LLM ↔ tools until a final answer.

Channel-agnostic. WhatsApp, voice, and the raw API all call `run_agent`.
"""
from __future__ import annotations

import json

from datetime import datetime
import zoneinfo

from . import llm, tools
from .config import settings

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = (
    "You are Nova, a private household assistant for Ruben and Méral. "
    "You help them run a shared plan: tasks/todos, calendar events, and important emails. "
    "Be concise and warm. When the user asks to change tasks or the calendar, use the tools "
    "rather than guessing. The current user of this conversation is: {user}. "
    "Attribute tasks to that user unless they name someone else. "
    "The current date and time is: {now}."
)


async def run_agent(user_message: str, *, user: str, history: list[dict] | None = None) -> str:
    """Run one turn: returns Nova's final text reply.

    `history` is a list of prior {role, content} messages (short-term memory).
    """
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_str = datetime.now(tz).isoformat()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT.format(user=user, now=now_str)}]

    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    specs = tools.tool_specs()

    for _ in range(MAX_TOOL_ITERATIONS):
        message = await llm.chat(messages, tools=specs)
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return message.get("content", "").strip()

        # Execute each requested tool and feed results back to the model.
        for call in tool_calls:
            fn = call["function"]
            fn_name = fn["name"]
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
                
            # CONFIRM-01: Intercept destructive or write action tools for confirmation
            if fn_name in ("create_event", "complete_task", "delete_event", "send_email"):
                confirmed = False
                if history:
                    # Find the last assistant message requesting confirmation
                    last_assistant_msg = None
                    for msg in reversed(history):
                        if msg.get("role") == "assistant":
                            last_assistant_msg = msg.get("content") or ""
                            break
                    if last_assistant_msg and "[CONFIRMATION_REQUIRED]" in last_assistant_msg:
                        user_confirm = user_message.strip().lower()
                        if any(w in user_confirm for w in ("yes", "confirm", "ok", "yep", "ja", "sure", "approve", "go ahead")):
                            confirmed = True
                
                if not confirmed:
                    title_info = args.get("title") or args.get("val") or ""
                    return f"[CONFIRMATION_REQUIRED] Would you like me to proceed with {fn_name} for '{title_info}'?"

            result = await tools.call_tool(fn["name"], args, user=user)
            messages.append({"role": "tool", "content": result})

    return "Sorry, I got stuck working on that — could you rephrase?"

