"""Tests for the email tool (IMAP/SMTP-backed, Phase 38).

Covers EMAIL-01: importance classification (hybrid keyword+LLM),
IMAP fetch shape and content, SMTP send success/failure,
IMAP protocol correctness (UID, BODY.PEEK), and flag-based dedup.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings, settings
from app.llm import ChatResult
from app.tools.email import (
    classify_importance,
    fetch_emails_imap,
    list_recent_emails,
    send_email_message,
    _mark_email_processed,
)


# ---------------------------------------------------------------------------
# D-01 / D-02 : nova_email property
# ---------------------------------------------------------------------------

def test_nova_email_property():
    """D-01/D-02: nova_email derives correctly from nova_domain."""
    s = Settings(nova_domain="7rb.nl")
    assert s.nova_email == "nova@7rb.nl"

    s2 = Settings()
    assert s2.nova_email == ""


# ---------------------------------------------------------------------------
# EMAIL-01 : Importance classification (hybrid keyword + LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_importance_keyword_dutch():
    """EMAIL-01: A Dutch keyword in the subject triggers important=True."""
    result = await classify_importance(
        "Factuur juli 2026", "billing@energy.nl", "Uw maandelijkse factuur"
    )
    assert result is True


@pytest.mark.asyncio
async def test_classify_importance_keyword_english():
    """EMAIL-01: An English keyword in the subject triggers important=True."""
    result = await classify_importance(
        "Invoice for July", "billing@energy.nl", "Your invoice is ready"
    )
    assert result is True


@pytest.mark.asyncio
async def test_classify_importance_keyword_preview():
    """EMAIL-01: A keyword in the preview text (not just subject) triggers important."""
    result = await classify_importance(
        "Newsletter", "school@edu.nl", "School holiday schedule for next year"
    )
    assert result is True  # 'school' keyword in preview


@pytest.mark.asyncio
async def test_classify_importance_falls_back_to_llm():
    """EMAIL-01: Non-keyword emails fall back to LLM classification."""
    with patch("app.tools.email.llm.chat", new_callable=AsyncMock) as llm_mock:
        llm_mock.return_value = ChatResult(message={"content": "Yes"})
        result = await classify_importance(
            "Random flyer", "marketing@store.com", "Check out our deals"
        )
        assert result is True
        llm_mock.assert_called_once()

        llm_mock.return_value = ChatResult(message={"content": "No"})
        result = await classify_importance(
            "Spam offer", "spammer@bad.com", "You won a prize"
        )
        assert result is False


@pytest.mark.asyncio
async def test_classify_importance_conservative_on_llm_error():
    """EMAIL-01: When the LLM call fails, classification defaults to True (conservative)."""
    with patch("app.tools.email.llm.chat", new_callable=AsyncMock) as llm_mock:
        llm_mock.side_effect = RuntimeError("LLM unavailable")
        result = await classify_importance(
            "Unknown subject", "unknown@test.com", "Some content"
        )
        assert result is True  # Conservative fallback


# ---------------------------------------------------------------------------
# D-15 : fetch_emails_imap mock data shape and content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_emails_imap_mock_shape():
    """D-15: fetch_emails_imap returns correct dict shape when IMAP host empty (mock)."""
    with patch.object(settings, "nova_imap_host", ""):
        result = await fetch_emails_imap(limit=10)

    assert isinstance(result, list)
    assert len(result) > 0

    for email in result:
        assert "id" in email
        assert "subject" in email
        assert "from" in email
        assert "preview" in email
        assert "unread" in email


@pytest.mark.asyncio
async def test_fetch_emails_imap_mock_content():
    """D-15: fetch_emails_imap mock data contains the 4 expected hardcoded emails."""
    with patch.object(settings, "nova_imap_host", ""):
        result = await fetch_emails_imap(limit=10)

    assert len(result) == 4

    subjects = [e["subject"] for e in result]
    assert any("School update" in s for s in subjects)
    assert any("CalDAV" in s for s in subjects)
    assert any("Factuur" in s for s in subjects)
    assert any("Spam" in s for s in subjects)


# ---------------------------------------------------------------------------
# D-14 : send_email tool success and failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_tool_success():
    """D-14: send_email_message returns success when SMTP responds 250."""
    mock_response = MagicMock()
    mock_response.code = 250
    mock_response.message = "OK"

    with patch("app.tools.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_response
        result = await send_email_message("test@example.com", "Test Subject", "Test body")

    assert result["success"] is True
    assert result["code"] == 250


@pytest.mark.asyncio
async def test_send_email_tool_failure():
    """D-14: send_email_message returns failure when SMTP responds 550."""
    mock_response = MagicMock()
    mock_response.code = 550
    mock_response.message = "Rejected"

    with patch("app.tools.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_response
        result = await send_email_message("test@example.com", "Test Subject", "Test body")

    assert result["success"] is False
    assert result["code"] == 550


@pytest.mark.asyncio
async def test_send_email_from_address():
    """D-04: send_email_message uses nova@{NOVA_DOMAIN} as From address."""
    mock_response = MagicMock()
    mock_response.code = 250
    mock_response.message = "OK"

    with patch.object(settings, "nova_domain", "test.com"), \
         patch("app.tools.email.aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = mock_response
        await send_email_message("to@example.com", "Subject", "Body")

        # Verify the EmailMessage passed to aiosmtplib.send has correct From header
        call_args = mock_send.call_args[0]
        message = call_args[0]  # First positional arg is the EmailMessage
        assert message["From"] == "nova@test.com"


# ---------------------------------------------------------------------------
# D-15 : IMAP protocol correctness — BODY.PEEK and UID operations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_imap_uses_body_peek():
    """D-15/Pitfall 2: IMAP FETCH uses BODY.PEEK (not bare BODY)."""
    mock_imap = MagicMock()
    mock_imap.wait_hello_from_server = AsyncMock()
    mock_imap.login = AsyncMock()
    mock_imap.select = AsyncMock()
    mock_imap.logout = AsyncMock()
    mock_imap.uid = AsyncMock()

    # uid("search", ...) returns one UID
    mock_imap.uid.side_effect = [
        ("OK", [b"42"]),                             # SEARCH
        ("OK", [(b"", b"Subject: Test\r\nFrom: x@y\r\nDate: now\r\n\r\n")]),  # FETCH
    ]

    with patch.object(settings, "nova_imap_host", "imap.example.com"), \
         patch("app.tools.email.aioimaplib.IMAP4_SSL") as imap_cls:
        imap_cls.return_value = mock_imap

        await fetch_emails_imap(limit=10)

        # Check that at least one uid() call used BODY.PEEK
        all_calls = [str(c) for c in mock_imap.uid.call_args_list]
        body_peek_calls = [c for c in all_calls if "BODY.PEEK" in c]
        body_bare_calls = [c for c in all_calls if "BODY[" in c and "BODY.PEEK" not in c]

        assert len(body_peek_calls) > 0, "No BODY.PEEK call found"
        assert len(body_bare_calls) == 0, f"Found bare BODY[] call: {body_bare_calls}"


@pytest.mark.asyncio
async def test_imap_uses_uid_not_seq():
    """D-15/Pitfall 1: IMAP operations use uid() method (not sequence numbers)."""
    mock_imap = MagicMock()
    mock_imap.wait_hello_from_server = AsyncMock()
    mock_imap.login = AsyncMock()
    mock_imap.select = AsyncMock()
    mock_imap.logout = AsyncMock()
    mock_imap.uid = AsyncMock()

    mock_imap.uid.side_effect = [
        ("OK", [b"42"]),
        ("OK", [(b"", b"Subject: Test\r\nFrom: x@y\r\nDate: now\r\n\r\n")]),
    ]

    with patch.object(settings, "nova_imap_host", "imap.example.com"), \
         patch("app.tools.email.aioimaplib.IMAP4_SSL") as imap_cls:
        imap_cls.return_value = mock_imap

        await fetch_emails_imap(limit=10)

        # Verify uid() was called (search, fetch use UID)
        assert mock_imap.uid.call_count >= 2, "Expected at least 2 uid() calls (SEARCH + FETCH)"

        # Verify no direct search/fetch/store on imap object (without uid)
        # These are the sequence-number variants that we must avoid
        if hasattr(mock_imap, "search"):
            mock_imap.search.assert_not_called()
        if hasattr(mock_imap, "fetch"):
            mock_imap.fetch.assert_not_called()
        if hasattr(mock_imap, "store"):
            mock_imap.store.assert_not_called()


# ---------------------------------------------------------------------------
# D-08 : _mark_email_processed sets correct IMAP flags
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_email_processed_flags():
    """D-08: _mark_email_processed calls STORE with $NovaProcessed flag."""
    mock_imap = MagicMock()
    mock_imap.wait_hello_from_server = AsyncMock()
    mock_imap.login = AsyncMock()
    mock_imap.logout = AsyncMock()
    mock_imap.uid = AsyncMock(return_value=("OK", [b""]))

    with patch.object(settings, "nova_imap_host", "imap.example.com"), \
         patch("app.tools.email.aioimaplib.IMAP4_SSL") as imap_cls:
        imap_cls.return_value = mock_imap

        await _mark_email_processed("99")

        # Verify uid("store", ...) was called
        store_calls = [
            c for c in mock_imap.uid.call_args_list
            if c[0][0] == "store"
        ]
        assert len(store_calls) >= 1, "Expected at least one uid('store', ...) call"

        # Check the first store call includes $NovaProcessed
        first_store_args = str(store_calls[0])
        assert "$NovaProcessed" in first_store_args, (
            f"Expected $NovaProcessed in STORE args: {first_store_args}"
        )


# ---------------------------------------------------------------------------
# EMAIL-02 : Querying important emails (adapted for IMAP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_recent_emails_shows_importance_tag():
    """EMAIL-02: Emails matching importance keywords show [IMPORTANT] in the listing."""
    mock_emails = [
        {"id": "msg_1", "subject": "School update: upcoming holidays", "from": "school@edu.nl", "preview": "Holiday info", "unread": True},
        {"id": "msg_3", "subject": "Factuur July 2026", "from": "billing@energy.nl", "preview": "Invoice ready", "unread": True},
    ]

    with patch("app.tools.email.fetch_emails_imap", new_callable=AsyncMock) as fetch_mock:
        fetch_mock.return_value = mock_emails
        result = await list_recent_emails()

        # 'School' and 'Factuur' keywords match → should be [IMPORTANT]
        assert "[IMPORTANT]" in result
        assert "School update" in result
        assert "Factuur" in result


@pytest.mark.asyncio
async def test_list_recent_emails_empty():
    """EMAIL-02: A listing with no emails returns a friendly empty message."""
    with patch(
        "app.tools.email.fetch_emails_imap", new_callable=AsyncMock
    ) as fetch_mock:
        fetch_mock.return_value = []
        result = await list_recent_emails()
        assert result == "No recent emails."
