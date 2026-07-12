"""The Nova agent loop: LLM ↔ tools until a final answer.

Channel-agnostic. WhatsApp, voice, and the raw API all call `run_agent`.
"""
from __future__ import annotations

import asyncio
import json
import re

from datetime import datetime
import zoneinfo

from . import llm, tools
from .audit import record_tool_call
from .config import settings
from .db import get_user_memories

_MAX_MUTATING_TOOLS = {"add_task", "complete_task", "create_event", "ha_call_service", "remember", "forget"}
MAX_HISTORY_MESSAGES = 20

_CONFIRM_WORDS = {"yes", "confirm", "ok", "okay", "yep", "ja", "sure", "approve"}
_DENY_WORDS = {"no", "not", "don't", "dont", "nope", "cancel", "stop", "unsure"}

SYSTEM_PROMPT = (
    "You are Nova, a private household assistant for Ruben and Méral. "
    "You help them run a shared plan: tasks/todos, calendar events, and important emails. "
    "Be concise and warm. When the user asks to change tasks or the calendar, use the tools "
    "rather than guessing. The current user of this conversation is: {user}. "
    "Attribute tasks to that user unless they name someone else. "
    "The current date and time is: {now}."
)


def _truncate_history(history: list[dict], max_messages: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """Keep the last max_messages, without starting the window on a `tool` reply.

    A `tool` message always immediately follows the `assistant` message whose
    `tool_calls` it answers; cutting between them sends Ollama a dangling pair.
    """
    if len(history) <= max_messages:
        return history
    cut = len(history) - max_messages
    while cut > 0 and history[cut].get("role") == "tool":
        cut -= 1
    return history[cut:]


def _is_confirmed(user_message: str) -> bool:
    """Whole-word match against confirm/deny vocabulary (not substring containment)."""
    tokens = set(re.findall(r"[a-z']+", user_message.strip().lower()))
    if tokens & _DENY_WORDS:
        return False
    return bool(tokens & _CONFIRM_WORDS) or "go ahead" in user_message.lower()


def _summarize_action(name: str, args: dict, result: str = "") -> str:
    """Produce a short human-readable summary of a tool invocation for the audit log."""
    if name == "add_task":
        assignee = args.get("assignee") or ""
        title = args.get("title") or ""
        return f"Added task '{title}' for {assignee}"
    elif name == "complete_task":
        title = args.get("title") or ""
        return f"Completed task '{title}'"
    elif name == "create_event":
        title = args.get("title") or args.get("summary") or ""
        return f"Created event '{title}'"
    elif name == "ha_call_service":
        domain = args.get("domain", "")
        service_name = args.get("service", "")
        target = args.get("target", "")
        return f"Called HA service {domain}.{service_name} on {target}"
    elif name == "remember":
        content = args.get("content", "")
        short = content[:60] + "..." if len(content) > 60 else content
        return f"Remembered: {short}"
    elif name == "forget":
        pattern = args.get("content_pattern", "")
        return f"Forget memory matching '{pattern}'"
    else:
        return f"'{name}' with {json.dumps(args)}"


async def run_agent(user_message: str, *, user: str, history: list[dict] | None = None) -> str:
    """Run one turn: returns Nova's final text reply.

    `history` is a list of prior {role, content} messages (short-term memory).
    """
    tz = zoneinfo.ZoneInfo(settings.nova_timezone)
    now_str = datetime.now(tz).isoformat()

    system_content = SYSTEM_PROMPT.format(user=user, now=now_str)
    memories_context = await get_user_memories(user)
    if memories_context:
        system_content += f"\n\nRelevant memories about {user} and the household:\n{memories_context}"

    messages: list[dict] = [{"role": "system", "content": system_content}]

    if history:
        messages.extend(_truncate_history(history))
    messages.append({"role": "user", "content": user_message})

    specs = tools.tool_specs()

    try:
        async with asyncio.timeout(settings.nova_max_turn_timeout):
            for _ in range(settings.nova_max_iterations):
                result = await llm.chat(messages, tools=specs)
                messages.append(result.message)

                tool_calls = result.message.get("tool_calls")
                if not tool_calls:
                    return (result.message.get("content") or "").strip()

                # Execute each requested tool and feed results back to the model.
                for call in tool_calls:
                    fn = call["function"]
                    fn_name = fn["name"]
                    args = fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = json.loads(args or "{}")

                    # CONFIRM-01: Intercept destructive or write action tools for confirmation
                    if fn_name in ("create_event", "complete_task", "ha_call_service", "forget"):
                        confirmed = False
                        if history:
                            # Find the last assistant message requesting confirmation
                            last_assistant_msg = None
                            for msg in reversed(history):
                                if msg.get("role") == "assistant":
                                    last_assistant_msg = msg.get("content") or ""
                                    break
                            if last_assistant_msg and "[CONFIRMATION_REQUIRED]" in last_assistant_msg:
                                confirmed = _is_confirmed(user_message)

                        if not confirmed:
                            # Record denied confirmation before early return
                            await record_tool_call(
                                user_name=user,
                                tool_name=fn_name,
                                action_summary=_summarize_action(fn_name, args),
                                status="denied",
                                confirmation_required=True,
                            )
                            detail = args.get("title") or args.get("content_pattern") or ""
                            return f"[CONFIRMATION_REQUIRED] Would you like me to proceed with {fn_name} for '{detail}'?"

                    result = await tools.call_tool(fn["name"], args, user=user)

                    # Record completed audit for mutating tools
                    if fn["name"] in _MAX_MUTATING_TOOLS:
                        await record_tool_call(
                            user_name=user,
                            tool_name=fn["name"],
                            action_summary=_summarize_action(fn["name"], args, result),
                            status="completed",
                            confirmation_required=(fn["name"] in ("create_event", "complete_task", "forget")),
                        )
                    messages.append({"role": "tool", "content": result})
    except TimeoutError:
        return "Sorry, I took too long to think about that. Could you try again?"

    return "Sorry, I got stuck working on that — could you rephrase?"

