"""Tool registry.

Tools are the household capabilities Nova can call (tasks, calendar, email).
Each tool is registered here and exposed to the LLM as an OpenAI-style function
definition. Phase 5 replaces the stub implementations with real integrations.
"""
from __future__ import annotations

from .base import TOOLS, Tool, tool  # noqa: F401
from . import tasks, calendar, email, home_assistant, memory, groceries, relay, chores  # noqa: F401  (import registers the tools)


def tool_specs() -> list[dict]:
    """OpenAI/Ollama-format function specs for every registered tool."""
    return [t.spec for t in TOOLS.values()]


async def call_tool(name: str, arguments: dict, *, user: str) -> str:
    """Execute a registered tool by name; returns a string result for the LLM."""
    if name not in TOOLS:
        return f"error: unknown tool '{name}'"
    return await TOOLS[name].run(arguments, user=user)
