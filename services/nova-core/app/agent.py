"""The Nova agent loop: LLM ↔ tools until a final answer.

Channel-agnostic. WhatsApp, voice, and the raw API all call `run_agent`.
"""
from __future__ import annotations

import json

from . import llm, tools

MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = (
    "You are Nova, a private household assistant for Ruben and Méral. "
    "You help them run a shared plan: tasks/todos, calendar events, and important emails. "
    "Be concise and warm. When the user asks to change tasks or the calendar, use the tools "
    "rather than guessing. The current user of this conversation is: {user}. "
    "Attribute tasks to that user unless they name someone else."
)


async def run_agent(user_message: str, *, user: str, history: list[dict] | None = None) -> str:
    """Run one turn: returns Nova's final text reply.

    `history` is a list of prior {role, content} messages (short-term memory).
    """
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT.format(user=user)}]
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
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            result = await tools.call_tool(fn["name"], args, user=user)
            messages.append({"role": "tool", "content": result})

    return "Sorry, I got stuck working on that — could you rephrase?"
