"""Grocery list tools — add/remove items from a household grocery list.

Grocery items are stored in a dedicated `grocery_items` table distinct from
`tasks` so the list is a first-class concept with its own lifecycle.
"""
from __future__ import annotations

from .base import tool
from ..db import get_pool
from .tasks import _get_user_uuid


@tool(
    name="add_grocery_item",
    description="Add an item to the shared household grocery list. "
                "If the item is already on the list (unpurchased), it won't be duplicated.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The grocery item to add, e.g. 'milk', 'bread', 'bananas'.",
            },
            "quantity": {
                "type": "string",
                "description": "Optional quantity, e.g. '2 liters', '1 bunch'.",
            },
        },
        "required": ["title"],
    },
)
async def add_grocery_item(title: str, user: str, quantity: str | None = None) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Auto-dedup: check for existing unpurchased item with same title (case-insensitive)
        existing = await conn.fetchrow(
            "SELECT id FROM grocery_items WHERE title ILIKE $1 AND purchased = false",
            title,
        )
        if existing:
            return f"'{title}' is already on the grocery list."

        added_by_uuid = await _get_user_uuid(conn, user)

        await conn.execute(
            """
            INSERT INTO grocery_items (title, quantity, added_by)
            VALUES ($1, $2, $3)
            """,
            title,
            quantity,
            added_by_uuid,
        )

    qty_suffix = f" ({quantity})" if quantity else ""
    return f"Added '{title}'{qty_suffix} to the grocery list."


@tool(
    name="list_groceries",
    description="Show all unpurchased items on the shared grocery list.",
    parameters={
        "type": "object",
        "properties": {},
    },
)
async def list_groceries() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.title, g.quantity, u.name AS added_by_name
            FROM grocery_items g
            LEFT JOIN users u ON g.added_by = u.id
            WHERE g.purchased = false
            ORDER BY g.added_at ASC
            """,
        )

    if not rows:
        return "The grocery list is empty."

    lines = []
    for i, row in enumerate(rows, 1):
        parts = [row["title"]]
        if row["quantity"]:
            parts.append(f"({row['quantity']})")
        parts.append(f"— added by {row['added_by_name'] or 'unknown'}")
        lines.append(f"{i}. {' '.join(parts)}")

    return "Grocery list:\n" + "\n".join(lines)


@tool(
    name="mark_purchased",
    description="Mark a grocery item as purchased, removing it from the active list.",
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title (or close match) of the purchased item.",
            },
        },
        "required": ["title"],
    },
)
async def mark_purchased(title: str, user: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        purchaser_uuid = await _get_user_uuid(conn, user)

        # Try exact match first
        res = await conn.execute(
            """
            UPDATE grocery_items
            SET purchased = true, purchased_at = now(), purchased_by = $2
            WHERE title = $1 AND purchased = false
            """,
            title,
            purchaser_uuid,
        )

        # If no exact match, try ILIKE substring
        if res == "UPDATE 0":
            res = await conn.execute(
                """
                UPDATE grocery_items
                SET purchased = true, purchased_at = now(), purchased_by = $2
                WHERE title ILIKE $1 AND purchased = false
                """,
                f"%{title}%",
                purchaser_uuid,
            )

    if res != "UPDATE 0":
        return f"Marked '{title}' as purchased."
    return f"Could not find '{title}' on the grocery list."
