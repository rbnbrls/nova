"""User-feedback detection, context capture, and Forgejo issue filing.

Every agent turn (success, stuck, error) can optionally capture conversation
context.  When a user signals feedback ("that was wrong" / 👎 reaction) the
module files a structured, redacted Forgejo issue tagged ``feedback``.

Per D-01 (text + reaction detection), D-02 (context capture),
D-03 (ForgejoClient integration), D-04 (feedback labels).
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("nova-core.feedback")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# D-01: Feedback text patterns — case-insensitive, optional "Nova, " prefix
_FEEDBACK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:nova,?\s+)?that\s+was\s+wrong\b", re.IGNORECASE),
    re.compile(r"(?:nova,?\s+)?that'?s\s+incorrect\b", re.IGNORECASE),
    re.compile(r"(?:nova,?\s+)?that(?:'?s| is)\s+not\s+right\b", re.IGNORECASE),
    re.compile(r"(?:nova,?\s+)?not\s+what\s+I\s+meant\b", re.IGNORECASE),
]

# D-01: Single reaction that signals feedback
_FEEDBACK_REACTIONS: set[str] = {"👎"}

# D-02: Max conversation turns to cache per user
_MAX_CONTEXT_TURNS: int = 3

# Redaction: E.164 phone number pattern (+ followed by 7-15 digits)
_PHONE_PATTERN = re.compile(r"\+\d{7,15}")

# Safe truncation limits for issue body
_MAX_MESSAGE_LENGTH = 500
_MAX_TOOL_CALLS_LENGTH = 1000

# ---------------------------------------------------------------------------
# TurnContext dataclass
# ---------------------------------------------------------------------------


@dataclass
class TurnContext:
    """A single agent-turn's context for feedback issue filing.

    All fields match the data shape from the tracer's ``AgentTrace``,
    providing enough context to diagnose what went wrong.
    """

    user_message: str
    """The user's original message (may be redacted later)."""

    agent_reply: str
    """Nova's final text reply."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """Each entry: ``{"name": str, "status": str, "duration_ms": int}``."""

    errors: list[dict[str, Any]] = field(default_factory=list)
    """Each entry: ``{"tool": str, "error": str}``."""

    iteration_count: int = 0
    """Number of LLM-tool round trips in this turn."""

    latency_ms: int = 0
    """Wall-clock milliseconds of the entire agent turn."""

    channel: str = "api"
    """Source channel: api / whatsapp / telegram / voice."""

    timestamp: str = ""
    """ISO-8601 timestamp of the turn."""


# ---------------------------------------------------------------------------
# FeedbackContext (per-user conversation cache)
# ---------------------------------------------------------------------------


class FeedbackContext:
    """Per-user ring buffer of recent conversation turns.

    Used by::

        feedback_context = FeedbackContext()
        feedback_context.capture("Ruben", turn)
        turns = feedback_context.get("Ruben")
    """

    def __init__(self) -> None:
        self.by_user: dict[str, list[TurnContext]] = {}

    def capture(self, user: str, turn: TurnContext) -> None:
        """Append *turn* for *user*, trimming to ``_MAX_CONTEXT_TURNS``."""
        turns = self.by_user.setdefault(user, [])
        turns.append(turn)
        # D-02: Keep only the last N turns
        if len(turns) > _MAX_CONTEXT_TURNS:
            self.by_user[user] = turns[-_MAX_CONTEXT_TURNS:]

    def get(self, user: str) -> list[TurnContext]:
        """Return recent turns for *user* (empty list for unknown users)."""
        return self.by_user.get(user, [])


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def detect_feedback_text(text: str | None) -> bool:
    """Return ``True`` if *text* matches a known feedback pattern.

    Per D-01: matches against a fixed set of case-insensitive patterns
    with an optional "Nova, " prefix.
    """
    if not text or not text.strip():
        return False
    for pattern in _FEEDBACK_PATTERNS:
        if pattern.search(text):
            return True
    return False


def detect_feedback_reaction(emoji: str | None) -> bool:
    """Return ``True`` if *emoji* is a feedback signal (👎).

    Per D-01: only the thumbs-down emoji triggers feedback.
    """
    return emoji in _FEEDBACK_REACTIONS


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def redact_context(turns: list[TurnContext]) -> list[TurnContext]:
    """Return a deep copy of *turns* with phone numbers replaced by ``[PHONE]``.

    Per D-03: strips E.164 phone numbers from ``user_message`` and
    ``agent_reply`` before the context crosses the network boundary
    to the Forgejo API.
    """
    redacted = copy.deepcopy(turns)
    for turn in redacted:
        turn.user_message = _PHONE_PATTERN.sub("[PHONE]", turn.user_message)
        turn.agent_reply = _PHONE_PATTERN.sub("[PHONE]", turn.agent_reply)
    return redacted


# ---------------------------------------------------------------------------
# Issue body builder
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len* characters, appending ``…`` if cut."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def build_issue_body(
    user: str,
    channel: str,
    turns: list[TurnContext],
    trigger: str,
) -> str:
    """Build a structured Markdown issue body from conversation context.

    Sections:
      1. Metadata (user, channel, trigger, timestamp, turn count)
      2. One section per conversation turn (redacted, truncated)

    Per D-03: message fields truncated to 500 chars, tool_call JSON to 1000.
    """
    lines: list[str] = []
    lines.append("## User Feedback Report")
    lines.append("")
    lines.append(f"- **User:** {user}")
    lines.append(f"- **Channel:** {channel}")
    lines.append(f"- **Trigger:** {trigger}")
    lines.append(f"- **Timestamp:** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- **Conversation turns captured:** {len(turns)}")
    lines.append("")

    for i, turn in enumerate(turns, 1):
        lines.append(f"---")
        lines.append(f"### Turn {i}")
        lines.append("")
        lines.append("**User message:**")
        lines.append(_truncate(turn.user_message, _MAX_MESSAGE_LENGTH))
        lines.append("")
        lines.append("**Agent reply:**")
        lines.append(_truncate(turn.agent_reply, _MAX_MESSAGE_LENGTH))
        lines.append("")

        if turn.tool_calls:
            tool_str = _truncate(
                str(turn.tool_calls), _MAX_TOOL_CALLS_LENGTH
            )
            lines.append("**Tool calls:**")
            lines.append(f"```json\n{tool_str}\n```")
            lines.append("")

        if turn.errors:
            lines.append("**Errors:**")
            for err in turn.errors:
                lines.append(f"- `{err.get('tool', '?')}`: {err.get('error', '?')}")
            lines.append("")

        lines.append(f"*Iteration {turn.iteration_count}, "
                      f"latency {turn.latency_ms}ms, "
                      f"channel {turn.channel}*")
        lines.append("")

    lines.append("---")
    lines.append("*Reported by Nova feedback module*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Issue filing (Forgejo)
# ---------------------------------------------------------------------------


async def file_feedback_issue(
    user: str,
    channel: str,
    turns: list[TurnContext],
    trigger: str,
) -> int | None:
    """File a feedback issue on the Forgejo repo.

    Per D-03: creates a ``ForgejoClient`` with settings from the app config.
    Per D-04: tags the issue with the ``feedback`` label.

    Returns the issue number on success, ``None`` on any exception
    (or if Forgejo is not configured).
    """
    from .config import settings  # D-03
    from .forgejo import ForgejoClient  # D-03

    # D-03: Skip silently if Forgejo is not configured
    if not settings.forgejo_url or not settings.forgejo_token:
        log.debug("Forgejo not configured — skipping feedback issue filing")
        return None

    # D-03: Redact before building the issue body
    redacted_turns = redact_context(turns)  # per D-03
    body = build_issue_body(user, channel, redacted_turns, trigger)
    title = f"User feedback from {user} ({channel})"

    client = ForgejoClient(
        base_url=settings.forgejo_url,
        repo=settings.forgejo_repo,
        token=settings.forgejo_token,
    )

    try:
        # D-04: Tag with feedback label
        issue_number = await client.create_issue(title, body, labels=["feedback"])
        log.info(
            "Feedback issue #%d filed for %s (%s) — trigger: %s",
            issue_number, user, channel, trigger,
        )
        return issue_number
    except Exception as exc:
        log.warning(
            "Failed to file feedback issue for %s (%s): %s",
            user, channel, exc,
        )
        return None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

#: Pre-initialised ``FeedbackContext`` shared by Plan 02 callers.
feedback_context = FeedbackContext()
"""Module-level singleton — imported by agent loop and channel handlers."""
