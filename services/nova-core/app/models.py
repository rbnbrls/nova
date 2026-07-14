"""OpenAI-compatible request/response schemas.

Home Assistant's OpenAI-conversation integration (Phase 6) targets /v1/chat/completions,
so Nova Core speaks just enough of that shape.
"""
from __future__ import annotations

import re
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
    # Nova extension: which voice room this request originates from.
    room: str | None = None


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
    channel: str = "whatsapp"
    channel_id: str = ""


class VerifyCodeRequest(BaseModel):
    user: str
    code: str
    channel_id: str = ""


class BriefingSettingsRequest(BaseModel):
    user: str
    morning_enabled: bool
    morning_time: str
    weekly_enabled: bool
    weekly_day: int
    weekly_time: str


class DNDSettingsRequest(BaseModel):
    user: str
    dnd_enabled: bool
    dnd_start: str
    dnd_end: str


class LinkWhatsAppStartRequest(BaseModel):
    user: str
    number: str  # E.164 format, no leading '+'


class LinkWhatsAppVerifyRequest(BaseModel):
    user: str
    code: str


class LinkTelegramStartRequest(BaseModel):
    user: str


class LinkTelegramVerifyRequest(BaseModel):
    user: str
    code: str


class DashboardChatRequest(BaseModel):
    user: str = "household"
    message: str


class DashboardChatResponse(BaseModel):
    reply: str


# ---------------------------------------------------------------------------
# Phase 41 — Model management request schemas
# ---------------------------------------------------------------------------

_MODEL_NAME_RE = re.compile(r"^[a-zA-Z0-9:_\-./]+$")


def validate_model_name(name: str) -> bool:
    """Return True if *name* matches the allowed model-name pattern."""
    return bool(_MODEL_NAME_RE.match(name))


class ModelSwitchRequest(BaseModel):
    model: str


class ModelPullRequest(BaseModel):
    model: str


class ModelDeleteRequest(BaseModel):
    model: str


# ---------------------------------------------------------------------------
# Phase 42 — Contact management request/response schemas
# ---------------------------------------------------------------------------

from uuid import UUID as _UUID
from datetime import datetime as _datetime
from pydantic import BaseModel as _BaseModel, Field as _Field


class ContactCreateRequest(_BaseModel):
    name: str
    notes: str | None = None


class ContactUpdateRequest(_BaseModel):
    name: str | None = None
    notes: str | None = None


class ContactEmailCreateRequest(_BaseModel):
    email: str
    type: str | None = None


class ContactPhoneCreateRequest(_BaseModel):
    phone: str
    type: str | None = None


class ContactAddressCreateRequest(_BaseModel):
    address: str
    type: str | None = None


class ContactEmailResponse(_BaseModel):
    id: str
    contact_id: str
    email: str
    type: str | None = None


class ContactPhoneResponse(_BaseModel):
    id: str
    contact_id: str
    phone: str
    type: str | None = None


class ContactAddressResponse(_BaseModel):
    id: str
    contact_id: str
    address: str
    type: str | None = None


class ContactResponse(_BaseModel):
    id: str
    name: str
    notes: str | None = None
    created_at: _datetime | None = None
    updated_at: _datetime | None = None
    emails: list[ContactEmailResponse] = _Field(default_factory=list)
    phones: list[ContactPhoneResponse] = _Field(default_factory=list)
    addresses: list[ContactAddressResponse] = _Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 43 — Planning (deterministic auto-scheduler) request/response schemas
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _PBaseModel, Field as _PField


class PlannedBlockCreate(_PBaseModel):
    task_id: str | None = None
    title: str
    planned_date: str  # ISO date, e.g. 2026-07-15
    start_time: str    # ISO datetime, e.g. 2026-07-15T09:00:00+02:00
    end_time: str      # ISO datetime
    is_occupied: bool = False
    source_event_uid: str | None = None


class PlannedBlockResponse(_PBaseModel):
    id: str
    task_id: str | None = None
    title: str
    planned_date: str
    start_time: str
    end_time: str
    is_occupied: bool = False
    source_event_uid: str | None = None
    created_at: str


class PlanRequest(_PBaseModel):
    user: str
    start_date: str  # ISO date
    end_date: str    # ISO date
    regenerate: bool = False


class PlanResponse(_PBaseModel):
    blocks: list[PlannedBlockResponse]
    generated_at: str



