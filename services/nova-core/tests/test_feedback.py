"""Unit tests for feedback module.

Follows the project's existing test patterns — uses AsyncMock for
ForgejoClient, direct settings patching for config-dependent paths,
and realistic test data matching TurnContext shapes.

RED phase: tests exist but fail because app/feedback.py does not exist yet.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.feedback import (
    TurnContext,
    detect_feedback_text,
    detect_feedback_reaction,
    FeedbackContext,
    redact_context,
    build_issue_body,
    file_feedback_issue,
    feedback_context,
)


def _sample_turn(**overrides) -> TurnContext:
    """Build a realistic TurnContext for testing."""
    defaults = dict(
        user_message="What's on the calendar?",
        agent_reply="You have one event today at 3pm.",
        tool_calls=[{"name": "get_calendar", "status": "completed", "duration_ms": 150}],
        errors=[],
        iteration_count=1,
        latency_ms=1200,
        channel="api",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(overrides)
    return TurnContext(**defaults)


# ------------------------------------------------------------------
# detect_feedback_text
# ------------------------------------------------------------------

class TestDetectFeedbackText:
    """per D-01: text pattern matching for feedback detection."""

    def test_matches_that_was_wrong(self):
        assert detect_feedback_text("that was wrong") is True

    def test_matches_nova_prefix(self):
        assert detect_feedback_text("Nova, that was wrong") is True
        assert detect_feedback_text("nova that was wrong") is True

    def test_matches_incorrect(self):
        assert detect_feedback_text("That's incorrect") is True
        assert detect_feedback_text("that is incorrect") is True

    def test_matches_not_right(self):
        assert detect_feedback_text("that is not right") is True
        assert detect_feedback_text("That's not right") is True

    def test_matches_not_what_i_meant(self):
        assert detect_feedback_text("not what I meant") is True
        assert detect_feedback_text("Nova, not what I meant") is True

    def test_no_match(self):
        assert detect_feedback_text("hello there") is False
        assert detect_feedback_text("what's the weather?") is False
        assert detect_feedback_text("add milk to the list") is False

    def test_empty_string(self):
        assert detect_feedback_text("") is False

    def test_whitespace_only(self):
        assert detect_feedback_text("   ") is False
        assert detect_feedback_text("\t\n") is False

    def test_case_insensitive(self):
        assert detect_feedback_text("THAT WAS WRONG") is True
        assert detect_feedback_text("That Was Wrong") is True

    def test_partial_word_no_match(self):
        """Ensure substrings don't false-positive."""
        assert detect_feedback_text("that wasn't my intention") is False
        assert detect_feedback_text("that's incorrectness") is False


# ------------------------------------------------------------------
# detect_feedback_reaction
# ------------------------------------------------------------------

class TestDetectFeedbackReaction:
    """per D-01: emoji reaction detection for feedback."""

    def test_thumbs_down(self):
        assert detect_feedback_reaction("👎") is True

    def test_thumbs_up(self):
        assert detect_feedback_reaction("👍") is False

    def test_empty_string(self):
        assert detect_feedback_reaction("") is False

    def test_none(self):
        assert detect_feedback_reaction(None) is False

    def test_other_emoji(self):
        assert detect_feedback_reaction("❤️") is False
        assert detect_feedback_reaction("😂") is False
        assert detect_feedback_reaction("🔥") is False


# ------------------------------------------------------------------
# FeedbackContext (per-user conversation context cache, D-02)
# ------------------------------------------------------------------

class TestFeedbackContext:
    """per D-02: per-user context capture with 3-turn limit."""

    def test_capture_and_get_context(self):
        ctx = FeedbackContext()
        turn1 = _sample_turn(user_message="hello")
        turn2 = _sample_turn(user_message="how are you")
        turn3 = _sample_turn(user_message="help me")

        ctx.capture("Ruben", turn1)
        ctx.capture("Ruben", turn2)
        ctx.capture("Ruben", turn3)

        turns = ctx.get("Ruben")
        assert len(turns) == 3
        assert turns[0].user_message == "hello"
        assert turns[2].user_message == "help me"

    def test_capture_enforces_max_turns(self):
        ctx = FeedbackContext()
        for i in range(5):
            ctx.capture("Ruben", _sample_turn(user_message=f"msg {i}"))

        turns = ctx.get("Ruben")
        assert len(turns) == 3
        assert turns[-1].user_message == "msg 4"

    def test_get_unknown_user_returns_empty(self):
        ctx = FeedbackContext()
        assert ctx.get("Unknown") == []

    def test_multiple_users_isolated(self):
        ctx = FeedbackContext()
        ctx.capture("Ruben", _sample_turn(user_message="hi"))
        ctx.capture("Meral", _sample_turn(user_message="hello"))

        assert len(ctx.get("Ruben")) == 1
        assert len(ctx.get("Meral")) == 1


# ------------------------------------------------------------------
# TurnContext dataclass
# ------------------------------------------------------------------

class TestTurnContext:
    """TurnContext carries all 8 fields from the tracer's AgentTrace shape."""

    def test_all_fields(self):
        now = datetime.now(timezone.utc).isoformat()
        turn = TurnContext(
            user_message="hello",
            agent_reply="hi there",
            tool_calls=[{"name": "test_tool"}],
            errors=[{"tool": "agent", "error": "something"}],
            iteration_count=2,
            latency_ms=500,
            channel="api",
            timestamp=now,
        )
        assert turn.user_message == "hello"
        assert turn.agent_reply == "hi there"
        assert turn.tool_calls == [{"name": "test_tool"}]
        assert turn.errors == [{"tool": "agent", "error": "something"}]
        assert turn.iteration_count == 2
        assert turn.latency_ms == 500
        assert turn.channel == "api"
        assert turn.timestamp == now


# ------------------------------------------------------------------
# redact_context
# ------------------------------------------------------------------

class TestRedactContext:
    """per D-03: phone-number redaction before issue filing."""

    def test_removes_phone_number(self):
        turn = _sample_turn(
            user_message="Call me at +31612345678",
            agent_reply="Your number +31612345678 is noted",
        )
        redacted = redact_context([turn])
        assert redacted[0].user_message == "Call me at [PHONE]"
        assert redacted[0].agent_reply == "Your number [PHONE] is noted"

    def test_multiple_phone_numbers(self):
        turn = _sample_turn(user_message="+31611111111 and +31622222222 are my numbers")
        redacted = redact_context([turn])
        assert redacted[0].user_message == "[PHONE] and [PHONE] are my numbers"

    def test_returns_deep_copy(self):
        original = _sample_turn(user_message="Call +31612345678")
        redacted = redact_context([original])
        # Original unchanged
        assert original.user_message == "Call +31612345678"
        # Redacted copy has [PHONE]
        assert redacted[0].user_message == "Call [PHONE]"
        # Different objects
        assert redacted[0] is not original

    def test_no_phone_number(self):
        turn = _sample_turn(user_message="Hello there")
        redacted = redact_context([turn])
        assert redacted[0].user_message == "Hello there"

    def test_empty_list(self):
        assert redact_context([]) == []

    def test_agent_reply_only_has_phone(self):
        turn = _sample_turn(user_message="clean", agent_reply="OK, saved +31698765432")
        redacted = redact_context([turn])
        assert redacted[0].user_message == "clean"
        assert redacted[0].agent_reply == "OK, saved [PHONE]"

    def test_short_numbers_unchanged(self):
        """Numbers shorter than 7 digits should not be redacted (not E.164)."""
        turn = _sample_turn(user_message="Call 123456")
        redacted = redact_context([turn])
        assert "123456" in redacted[0].user_message
        assert "[PHONE]" not in redacted[0].user_message


# ------------------------------------------------------------------
# build_issue_body
# ------------------------------------------------------------------

class TestBuildIssueBody:
    """per D-03: Structured issue body with redacted turns."""

    def test_structure_contains_all_sections(self):
        turns = [
            _sample_turn(user_message="that was wrong", agent_reply="Sorry about that"),
        ]
        body = build_issue_body("Ruben", "api", turns, "text: that was wrong")

        assert "Ruben" in body
        assert "api" in body
        assert "text: that was wrong" in body
        assert "that was wrong" in body
        assert "Sorry about that" in body

    def test_truncates_long_fields(self):
        long_msg = "x" * 1000
        long_tool_calls = [{"data": "y" * 2000}]
        turns = [_sample_turn(user_message=long_msg, tool_calls=long_tool_calls)]
        body = build_issue_body("Ruben", "api", turns, "test")

        # Message should be truncated to 500 chars
        assert ("x" * 500) in body
        # Should not have the full 1000 chars
        assert ("x" * 1000) not in body

    def test_multiple_turns(self):
        turns = [
            _sample_turn(user_message="first turn", agent_reply="first reply"),
            _sample_turn(user_message="second turn", agent_reply="second reply"),
        ]
        body = build_issue_body("Meral", "whatsapp", turns, "reaction: 👎")

        assert "Meral" in body
        assert "whatsapp" in body
        assert "first turn" in body
        assert "second turn" in body
        assert "reaction: 👎" in body


# ------------------------------------------------------------------
# file_feedback_issue (D-03, D-04)
# ------------------------------------------------------------------

class TestFileFeedbackIssue:
    """per D-03/D-04: Forgejo issue filing with feedback label."""

    @pytest.mark.asyncio
    async def test_success_returns_issue_number(self, monkeypatch):
        """Creates a Forgejo issue and returns the number."""
        from app.config import settings
        monkeypatch.setattr(settings, "forgejo_url", "https://git.example.com")
        monkeypatch.setattr(settings, "forgejo_token", "test-token")

        with patch("app.forgejo.ForgejoClient.create_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 42
            result = await file_feedback_issue("Ruben", "api", [], "text: test")
            assert result == 42
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert kwargs.get("labels") == ["feedback"]

    @pytest.mark.asyncio
    async def test_not_configured_returns_none(self, monkeypatch):
        """Returns None when forgejo_url or forgejo_token is empty."""
        from app.config import settings
        monkeypatch.setattr(settings, "forgejo_url", "")
        monkeypatch.setattr(settings, "forgejo_token", "")

        with patch("app.forgejo.ForgejoClient.create_issue", new_callable=AsyncMock) as mock_create:
            result = await file_feedback_issue("Ruben", "api", [], "text: test")
            assert result is None
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, monkeypatch):
        """Returns None when ForgejoClient raises ForgejoError."""
        from app.config import settings
        from app.forgejo import ForgejoError
        monkeypatch.setattr(settings, "forgejo_url", "https://git.example.com")
        monkeypatch.setattr(settings, "forgejo_token", "test-token")

        with patch("app.forgejo.ForgejoClient.create_issue", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = ForgejoError(500, "Internal Server Error")
            result = await file_feedback_issue("Ruben", "api", [], "text: test")
            assert result is None

    @pytest.mark.asyncio
    async def test_labels_include_feedback(self, monkeypatch):
        """Verifies the feedback label is passed to ForgejoClient.create_issue."""
        from app.config import settings
        monkeypatch.setattr(settings, "forgejo_url", "https://git.example.com")
        monkeypatch.setattr(settings, "forgejo_token", "test-token")

        with patch("app.forgejo.ForgejoClient.create_issue", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = 99
            result = await file_feedback_issue("Ruben", "api", [], "text: test")
            assert result == 99
            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert "labels" in kwargs
            assert "feedback" in kwargs["labels"]

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_none(self, monkeypatch):
        """Returns None on any unexpected exception (catches all)."""
        from app.config import settings
        monkeypatch.setattr(settings, "forgejo_url", "https://git.example.com")
        monkeypatch.setattr(settings, "forgejo_token", "test-token")

        with patch("app.forgejo.ForgejoClient.create_issue", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = RuntimeError("Something unexpected")
            result = await file_feedback_issue("Ruben", "api", [], "text: test")
            assert result is None


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

class TestFeedbackContextSingleton:
    """feedback_context is a pre-initialized FeedbackContext instance."""

    def test_is_feedback_context_instance(self):
        assert isinstance(feedback_context, FeedbackContext)
