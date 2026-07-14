"""Tests for the CardDAV sync module — VCF formatting + mocked sync."""
from __future__ import annotations

from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contacts_sync import (
    _build_vcard,
    _escape_vcf,
    _parse_vcard_uid,
    sync_contact,
    delete_contact_vcard,
    sync_all_contacts,
)


def _make_contact(
    name: str = "John Doe",
    notes: str | None = None,
    emails: list | None = None,
    phones: list | None = None,
    addresses: list | None = None,
    contact_id: str | None = None,
) -> dict:
    uid = contact_id or "550e8400-e29b-41d4-a716-446655440000"
    return {
        "id": UUID(uid),
        "name": name,
        "notes": notes,
        "emails": emails or [],
        "phones": phones or [],
        "addresses": addresses or [],
        "created_at": None,
        "updated_at": None,
    }


class TestVCardBuilding:
    def test_basic_contact(self):
        contact = _make_contact("John Doe")
        vcard = _build_vcard(contact)
        assert "BEGIN:VCARD" in vcard
        assert "VERSION:3.0" in vcard
        assert "FN:John Doe" in vcard
        assert "N:Doe;John;;;" in vcard
        assert "UID:550e8400-e29b-41d4-a716-446655440000" in vcard
        assert "REV:" in vcard
        assert "END:VCARD" in vcard

    def test_contact_with_emails(self):
        contact = _make_contact(
            "Jane Doe",
            emails=[{"id": 1, "email": "jane@example.com", "type": "WORK"}],
        )
        vcard = _build_vcard(contact)
        assert "EMAIL;TYPE=WORK:jane@example.com" in vcard

    def test_contact_with_phones(self):
        contact = _make_contact(
            "Bob Smith",
            phones=[{"id": 1, "phone": "+1234567890", "type": "CELL"}],
        )
        vcard = _build_vcard(contact)
        assert "TEL;TYPE=CELL:+1234567890" in vcard

    def test_contact_with_address(self):
        contact = _make_contact(
            "Alice",
            addresses=[{"id": 1, "address": "123 Main St", "type": "HOME"}],
        )
        vcard = _build_vcard(contact)
        assert "ADR;TYPE=HOME:;;123 Main St;;;;" in vcard

    def test_contact_with_notes(self):
        contact = _make_contact("Test", notes="This is a note with a semicolon; and comma, and newline\nhere")
        vcard = _build_vcard(contact)
        assert "NOTE:" in vcard
        assert "semicolon\\;" in vcard
        assert "comma\\," in vcard
        assert "newline" in vcard

    def test_empty_name_handling(self):
        contact = _make_contact("")
        vcard = _build_vcard(contact)
        assert "FN:" in vcard
        assert "N:;;;;" in vcard

    def test_vcard_reversible(self):
        contact = _make_contact("Reversible Test")
        vcard = _build_vcard(contact)
        uid = _parse_vcard_uid(vcard)
        assert uid == str(contact["id"])

    def test_escape_vcf_special_chars(self):
        assert _escape_vcf(None) == ""
        assert _escape_vcf("") == ""
        assert _escape_vcf("test") == "test"
        assert _escape_vcf("a;b") == "a\\;b"
        assert _escape_vcf("a,b") == "a\\,b"
        assert _escape_vcf("a\\b") == "a\\\\b"
        assert _escape_vcf("a\nb") == "a\\n b"


def _mock_client(put_result=None, delete_result=None):
    """Build a mock httpx client configured for async context manager usage."""
    mock_client = MagicMock()
    mock_client.is_closed = False
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    if put_result is not None:
        mock_client.put = AsyncMock(return_value=put_result)
    if delete_result is not None:
        mock_client.delete = AsyncMock(return_value=delete_result)

    return mock_client


class TestContactSync:
    @pytest.mark.asyncio
    async def test_sync_contact_puts_vcard(self):
        contact = _make_contact("Sync Test", contact_id="11111111-1111-1111-1111-111111111111")
        mock_put = MagicMock()
        mock_put.is_success = True
        mock_client = _mock_client(put_result=mock_put)

        with patch("app.contacts_sync.httpx.AsyncClient", return_value=mock_client):
            with patch("app.contacts_sync.settings") as mock_settings:
                mock_settings.caldav_url = "http://radicale:5232/"
                mock_settings.caldav_username = "nova"
                mock_settings.caldav_password = "secret"
                with patch("app.contacts_sync._ensure_address_book", AsyncMock(return_value="/dav/nova-household/")):
                    with patch("app.contacts.get_contact") as mock_get:
                        mock_get.return_value = contact
                        result = await sync_contact("11111111-1111-1111-1111-111111111111")
                        assert result is True

    @pytest.mark.asyncio
    async def test_sync_deleted_contact_returns_false(self):
        with patch("app.contacts_sync.settings") as mock_settings:
            mock_settings.caldav_url = "http://radicale:5232/"
            mock_settings.caldav_username = "nova"
            mock_settings.caldav_password = "secret"
            with patch("app.contacts.get_contact") as mock_get:
                mock_get.return_value = None
                result = await sync_contact("non-existent-id")
                assert result is False

    @pytest.mark.asyncio
    async def test_delete_contact_vcard(self):
        mock_delete = MagicMock()
        mock_delete.is_success = True
        mock_delete.status_code = 204
        mock_client = _mock_client(delete_result=mock_delete)

        with patch("app.contacts_sync.httpx.AsyncClient", return_value=mock_client):
            with patch("app.contacts_sync.settings") as mock_settings:
                mock_settings.caldav_url = "http://radicale:5232/"
                mock_settings.caldav_username = "nova"
                mock_settings.caldav_password = "secret"
                with patch("app.contacts_sync._ensure_address_book", AsyncMock(return_value="/dav/nova-household/")):
                    result = await delete_contact_vcard("11111111-1111-1111-1111-111111111111")
                    assert result is True

    @pytest.mark.asyncio
    async def test_sync_all_contacts(self):
        contacts = [
            _make_contact("Alice", contact_id="11111111-1111-1111-1111-111111111111"),
            _make_contact("Bob", contact_id="22222222-2222-2222-2222-222222222222"),
        ]

        mock_put = MagicMock()
        mock_put.is_success = True
        mock_client = _mock_client(put_result=mock_put)

        with patch("app.contacts_sync.httpx.AsyncClient", return_value=mock_client):
            with patch("app.contacts_sync.settings") as mock_settings:
                mock_settings.caldav_url = "http://radicale:5232/"
                mock_settings.caldav_username = "nova"
                mock_settings.caldav_password = "secret"
                with patch("app.contacts_sync._ensure_address_book", AsyncMock(return_value="/dav/nova-household/")):
                    with patch("app.contacts.list_contacts") as mock_list:
                        mock_list.return_value = contacts
                        result = await sync_all_contacts()
                        assert result["synced"] == 2
                        assert result["failed"] == 0
                        assert result["total"] == 2
