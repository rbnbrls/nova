"""LLM-callable contact management tools."""
from __future__ import annotations

from .base import tool
from ..contacts import (
    get_contact as _get_contact,
    list_contacts as _list_contacts,
    create_contact as _create_contact,
    delete_contact as _delete_contact,
)


@tool(
    name="add_contact",
    description="Add a new household contact.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Full name of the contact."},
            "notes": {"type": "string", "description": "Optional notes about the contact."},
        },
        "required": ["name"],
    },
)
async def add_contact(name: str, notes: str | None = None) -> str:
    row = await _create_contact(name, notes)
    if row:
        return f"Added contact '{row['name']}' (id: {row['id']})."
    return "Error: Failed to create contact."


@tool(
    name="list_contacts",
    description="List household contacts, optionally filtered by name search.",
    parameters={
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Optional name search filter."},
        },
    },
)
async def list_contacts(search: str | None = None) -> str:
    contacts = await _list_contacts(search)
    if not contacts:
        return "No contacts found."
    lines = [f"- {c['name']} (id: {c['id']})" for c in contacts]
    return "Contacts:\n" + "\n".join(lines)


@tool(
    name="delete_contact",
    description="Delete a household contact by name (first match).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the contact to delete."},
        },
        "required": ["name"],
    },
)
async def delete_contact(name: str) -> str:
    contacts = await _list_contacts(name)
    if not contacts:
        return f"Error: No contact found with name '{name}'."
    cid = contacts[0]["id"]
    ok = await _delete_contact(cid)
    if ok:
        return f"Deleted contact '{contacts[0]['name']}'."
    return f"Error: Failed to delete contact '{name}'."
