"""Tool primitives: a decorator that registers async functions as LLM-callable tools."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable

# name -> Tool
TOOLS: dict[str, "Tool"] = {}

ToolFn = Callable[..., Awaitable[str]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the arguments object
    fn: ToolFn

    @property
    def spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def run(self, arguments: dict, *, user: str) -> str:
        # Only pass through arguments the function actually declares.
        sig = inspect.signature(self.fn)
        kwargs = {k: v for k, v in arguments.items() if k in sig.parameters}
        if "user" in sig.parameters:
            kwargs["user"] = user
        try:
            return await self.fn(**kwargs)
        except Exception as exc:  # surface errors to the model, don't crash the loop
            return f"error: {exc}"


def tool(name: str, description: str, parameters: dict) -> Callable[[ToolFn], ToolFn]:
    """Register an async function as a tool."""

    def decorator(fn: ToolFn) -> ToolFn:
        TOOLS[name] = Tool(name=name, description=description, parameters=parameters, fn=fn)
        return fn

    return decorator
