"""OpenAI-compatible request/response schemas.

Home Assistant's OpenAI-conversation integration (Phase 6) targets /v1/chat/completions,
so Nova Core speaks just enough of that shape.
"""
from __future__ import annotations

import time
import uuid

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    # Nova extension: which household user this conversation belongs to.
    user: str | None = None


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:24]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[Choice]


class RequestCodeRequest(BaseModel):
    user: str
    number: str


class VerifyCodeRequest(BaseModel):
    user: str
    code: str

