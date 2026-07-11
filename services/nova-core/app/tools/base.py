"""Tool primitives: a decorator that registers async functions as LLM-callable tools."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable
import jsonschema

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
        # Validate against JSON Schema
        try:
            jsonschema.validate(instance=arguments, schema=self.parameters)
        except jsonschema.ValidationError as err:
            return f"validation error: {err.message}"

        # Reject any arguments not declared in the tool's parameter properties
        declared_params = self.parameters.get("properties", {})
        for k in arguments:
            if k not in declared_params:
                return f"validation error: unknown argument '{k}'"

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
