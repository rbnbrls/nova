"""Tests for the email tool (MS Graph-backed).

Covers EMAIL-01 through EMAIL-03: importance classification (hybrid
keyword+LLM), querying important emails, and Graph URL scoping.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.llm import ChatResult
from app.tools.email import (
    classify_importance,
    fetch_emails_from_graph,
    list_recent_emails,
)


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
# EMAIL-02 : Querying important emails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_recent_emails_shows_importance_tag():
    """EMAIL-02: Emails matching importance keywords show [IMPORTANT] in the listing."""
    with patch("app.tools.email.llm.chat", new_callable=AsyncMock) as llm_mock:
        llm_mock.return_value = {"content": "No"}  # non-keyword emails = not important

        result = await list_recent_emails()

        # 'School' and 'Factuur' keywords match → should be [IMPORTANT]
        assert "[IMPORTANT]" in result
        assert "School update" in result
        assert "Factuur" in result


@pytest.mark.asyncio
async def test_list_recent_emails_empty():
    """EMAIL-02: A listing with no emails returns a friendly empty message."""
    with patch(
        "app.tools.email.fetch_emails_from_graph", new_callable=AsyncMock
    ) as fetch_mock:
        fetch_mock.return_value = []
        result = await list_recent_emails()
        assert result == "No recent emails."


# ---------------------------------------------------------------------------
# EMAIL-03 : MS Graph URL scoped to shared mailbox
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_graph_url_uses_mailbox_email():
    """EMAIL-03: The Graph API URL uses the shared mailbox email, not /me."""
    mailbox = "household@example.com"
    with patch.object(settings, "azure_mailbox_email", mailbox):
        with patch(
            "app.tools.email._get_access_token", new_callable=AsyncMock
        ) as token_mock:
            token_mock.return_value = "fake-token"
            with patch(
                "app.tools.email.httpx.AsyncClient"
            ) as client_cls_mock:
                client_instance = AsyncMock()
                client_instance.__aenter__.return_value = client_instance
                client_cls_mock.return_value = client_instance
                resp_mock = MagicMock()
                resp_mock.status_code = 200
                resp_mock.json.return_value = {"value": []}
                client_instance.get.return_value = resp_mock

                await fetch_emails_from_graph()

                # Verify the URL used in the GET request
                url_used = client_instance.get.call_args[0][0]
                assert mailbox in url_used
                assert "graph.microsoft.com" in url_used
                assert "/users/" in url_used
                assert "/me/" not in url_used


@pytest.mark.asyncio
async def test_graph_url_not_tenant_wide():
    """EMAIL-03: The URL does NOT use a tenant-wide endpoint."""
    mailbox = "household@example.com"
    with patch.object(settings, "azure_mailbox_email", mailbox):
        with patch(
            "app.tools.email._get_access_token", new_callable=AsyncMock
        ) as token_mock:
            token_mock.return_value = "fake-token"
            with patch(
                "app.tools.email.httpx.AsyncClient"
            ) as client_cls_mock:
                client_instance = AsyncMock()
                client_instance.__aenter__.return_value = client_instance
                client_cls_mock.return_value = client_instance
                resp_mock = MagicMock()
                resp_mock.status_code = 200
                resp_mock.json.return_value = {"value": []}
                client_instance.get.return_value = resp_mock

                await fetch_emails_from_graph()

                url_used = client_instance.get.call_args[0][0]
                # Should reference the specific mailbox, not a tenant-wide query
                assert "users" in url_used
                # Ensure no tenant-wide patterns
                assert "adminconsent" not in url_used
