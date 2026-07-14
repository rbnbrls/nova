"""Contact repository — shared household address book, independent of Nova user table."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from .db import get_pool

log = logging.getLogger("nova-core.contacts")


async def create_contact(name: str, notes: str | None = None) -> dict | None:
    """Create a new contact and return its row, or None on failure."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO contacts (name, notes) VALUES ($1, $2) RETURNING id, name, notes, created_at, updated_at",
            name, notes
        )
    if row:
        asyncio.create_task(_sync_contact_after_crud(str(row["id"])))
    return row


async def get_contact(contact_id: str | UUID) -> dict | None:
    """Fetch a contact by id with all sub-entities (emails, phones, addresses)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT c.id, c.name, c.notes, c.created_at, c.updated_at,
                   COALESCE(json_agg(DISTINCT jsonb_build_object('id', ce.id, 'email', ce.email, 'type', ce.type)) FILTER (WHERE ce.id IS NOT NULL), '[]'::json) AS emails,
                   COALESCE(json_agg(DISTINCT jsonb_build_object('id', cp.id, 'phone', cp.phone, 'type', cp.type)) FILTER (WHERE cp.id IS NOT NULL), '[]'::json) AS phones,
                   COALESCE(json_agg(DISTINCT jsonb_build_object('id', ca.id, 'address', ca.address, 'type', ca.type)) FILTER (WHERE ca.id IS NOT NULL), '[]'::json) AS addresses
            FROM contacts c
            LEFT JOIN contact_emails ce ON ce.contact_id = c.id
            LEFT JOIN contact_phones cp ON cp.contact_id = c.id
            LEFT JOIN contact_addresses ca ON ca.contact_id = c.id
            WHERE c.id = $1::uuid
            GROUP BY c.id
            """,
            contact_id
        )


async def list_contacts(search: str | None = None) -> list[dict]:
    """List all contacts, optionally filtered by name search."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if search:
            rows = await conn.fetch(
                "SELECT id, name, notes, created_at, updated_at FROM contacts WHERE name ILIKE $1 ORDER BY name ASC",
                f"%{search}%"
            )
        else:
            rows = await conn.fetch(
                "SELECT id, name, notes, created_at, updated_at FROM contacts ORDER BY name ASC"
            )
        return [dict(row) for row in rows]


async def update_contact(contact_id: str | UUID, name: str | None = None, notes: str | None = None) -> dict | None:
    """Update a contact's name and/or notes. Returns updated row or None if no changes requested."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if name is None and notes is None:
            return await conn.fetchrow(
                "SELECT id, name, notes, created_at, updated_at FROM contacts WHERE id = $1::uuid",
                contact_id
            )
        row = await conn.fetchrow(
            "UPDATE contacts SET name = COALESCE($1, name), notes = COALESCE($2, notes), updated_at = now() WHERE id = $3::uuid RETURNING id, name, notes, created_at, updated_at",
            name, notes, contact_id
        )
    if row and (name is not None or notes is not None):
        asyncio.create_task(_sync_contact_after_crud(str(row["id"])))
    return row


async def delete_contact(contact_id: str | UUID) -> bool:
    """Delete a contact by id. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        res = await conn.execute("DELETE FROM contacts WHERE id = $1::uuid", contact_id)
    if res != "DELETE 0":
        asyncio.create_task(_delete_contact_vcard_after_crud(str(contact_id)))
    return res != "DELETE 0"


async def add_email(contact_id: str | UUID, email: str, type: str | None = None) -> dict:
    """Add an email to a contact. Returns the created row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO contact_emails (contact_id, email, type) VALUES ($1::uuid, $2, $3) RETURNING id, contact_id, email, type",
            contact_id, email, type
        )
    asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return row


async def add_phone(contact_id: str | UUID, phone: str, type: str | None = None) -> dict:
    """Add a phone number to a contact. Returns the created row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO contact_phones (contact_id, phone, type) VALUES ($1::uuid, $2, $3) RETURNING id, contact_id, phone, type",
            contact_id, phone, type
        )
    asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return row


async def add_address(contact_id: str | UUID, address: str, type: str | None = None) -> dict:
    """Add an address to a contact. Returns the created row."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO contact_addresses (contact_id, address, type) VALUES ($1::uuid, $2, $3) RETURNING id, contact_id, address, type",
            contact_id, address, type
        )
    asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return row


async def remove_email(email_id: str | UUID) -> bool:
    """Delete an email by id. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        contact_id = await conn.fetchval("SELECT contact_id FROM contact_emails WHERE id = $1::uuid", email_id)
        res = await conn.execute("DELETE FROM contact_emails WHERE id = $1::uuid", email_id)
    if contact_id and res != "DELETE 0":
        asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return res != "DELETE 0"


async def remove_phone(phone_id: str | UUID) -> bool:
    """Delete a phone number by id. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        contact_id = await conn.fetchval("SELECT contact_id FROM contact_phones WHERE id = $1::uuid", phone_id)
        res = await conn.execute("DELETE FROM contact_phones WHERE id = $1::uuid", phone_id)
    if contact_id and res != "DELETE 0":
        asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return res != "DELETE 0"


async def remove_address(address_id: str | UUID) -> bool:
    """Delete an address by id. Returns True if a row was deleted."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        contact_id = await conn.fetchval("SELECT contact_id FROM contact_addresses WHERE id = $1::uuid", address_id)
        res = await conn.execute("DELETE FROM contact_addresses WHERE id = $1::uuid", address_id)
    if contact_id and res != "DELETE 0":
        asyncio.create_task(_sync_contact_after_crud(str(contact_id)))
    return res != "DELETE 0"



async def _sync_contact_after_crud(contact_id: str) -> None:
    try:
        from .contacts_sync import sync_contact

        await sync_contact(contact_id)
    except Exception as exc:
        log.warning("CardDAV sync after CRUD failed for %s: %s", contact_id, exc)


async def _delete_contact_vcard_after_crud(contact_id: str) -> None:
    try:
        from .contacts_sync import delete_contact_vcard

        await delete_contact_vcard(contact_id)
    except Exception as exc:
        log.warning("CardDAV delete after CRUD failed for %s: %s", contact_id, exc)
