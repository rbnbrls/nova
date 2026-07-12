"""Tests for the grocery list tools and message relay tool.

Covers HC-01, HC-03: grocery list (add, list, mark purchased) and
message relay with sender attribution and recipient validation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.groceries import add_grocery_item, list_groceries, mark_purchased
from app.tools.relay import relay_message


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    """Build an asyncpg pool mock that yields *mock_conn* via acquire()."""
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


async def _fetchrow_side_effect(query: str, *params: str) -> dict | None:
    """Simulate asyncpg fetchrow for the user-lookup queries used by groceries."""
    if params:
        name = params[0]
        if name in ("Ruben", "Meral", "household"):
            return {"id": f"uuid-{name.lower()}"}
        return None
    if "household" in query:
        return {"id": "uuid-household"}
    return None


# ---------------------------------------------------------------------------
# Grocery: add_grocery_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_grocery_item_creates():
    """Insert succeeds, returns confirmation, uses grocery_items table."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect  # for dedup check + user lookup
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_grocery_item("milk", user="Ruben")
        assert result == "Added 'milk' to the grocery list."

        # Verify the dedup SELECT happened
        dedup_sql = conn.fetchrow.call_args_list[0][0][0]
        assert "grocery_items" in dedup_sql
        assert "purchased = false" in dedup_sql

        # Verify INSERT went to grocery_items table
        insert_sql = conn.execute.call_args[0][0]
        assert "INSERT INTO grocery_items" in insert_sql


@pytest.mark.asyncio
async def test_add_grocery_item_auto_dedup():
    """Existing unpurchased item with same title returns 'already on list', no second INSERT."""
    conn = AsyncMock()
    # First fetchrow (dedup check) returns a match
    conn.fetchrow.side_effect = [
        {"id": "uuid-existing"},  # dedup: found matching unpurchased item
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_grocery_item("milk", user="Ruben")
        assert result == "'milk' is already on the grocery list."

        # No INSERT should be executed
        assert conn.execute.call_count == 0


@pytest.mark.asyncio
async def test_add_grocery_item_does_not_dedup_against_purchased():
    """Same title but purchased=true still allows new entry."""
    conn = AsyncMock()
    # dedup check: no existing unpurchased item found
    conn.fetchrow.side_effect = [
        None,  # dedup: no unpurchased match
        {"id": "uuid-ruben"},  # user lookup
    ]
    conn.execute.return_value = "INSERT 0 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_grocery_item("milk", user="Ruben")
        assert result == "Added 'milk' to the grocery list."
        assert conn.execute.call_count == 1


# ---------------------------------------------------------------------------
# Grocery: list_groceries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_groceries_shows_active_items():
    """Returns formatted list of unpurchased items."""
    conn = AsyncMock()
    conn.fetch.return_value = [
        {"title": "Milk", "quantity": "2 liters", "added_by_name": "Ruben"},
        {"title": "Bread", "quantity": None, "added_by_name": "Meral"},
    ]

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_groceries()
        assert "Grocery list:" in result
        assert "1. Milk (2 liters) — added by Ruben" in result
        assert "2. Bread — added by Meral" in result


@pytest.mark.asyncio
async def test_list_groceries_empty():
    """No items returns 'The grocery list is empty.'"""
    conn = AsyncMock()
    conn.fetch.return_value = []

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_groceries()
        assert result == "The grocery list is empty."


# ---------------------------------------------------------------------------
# Grocery: mark_purchased
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_purchased_exact_match():
    """Exact title match marks purchased."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "UPDATE 1"

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await mark_purchased("milk", user="Ruben")
        assert result == "Marked 'milk' as purchased."

        exact_sql = conn.execute.call_args[0][0]
        assert "title = $1" in exact_sql
        assert "purchased_by" in exact_sql


@pytest.mark.asyncio
async def test_mark_purchased_ilike_fallback():
    """Exact fails, ILIKE succeeds."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.side_effect = ["UPDATE 0", "UPDATE 1"]  # exact fails, ILIKE succeeds

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await mark_purchased("milk", user="Ruben")
        assert result == "Marked 'milk' as purchased."

        call_sqls = [c[0][0] for c in conn.execute.call_args_list]
        assert "title = $1" in call_sqls[0]
        assert "title ILIKE" in call_sqls[1]
        assert conn.execute.call_count == 2


@pytest.mark.asyncio
async def test_mark_purchased_not_found():
    """No match returns Could not find."""
    conn = AsyncMock()
    conn.fetchrow.side_effect = _fetchrow_side_effect
    conn.execute.return_value = "UPDATE 0"  # both exact and ILIKE fail

    pool = _make_mock_pool(conn)

    with patch("app.tools.groceries.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await mark_purchased("nonexistent", user="Ruben")
        assert "Could not find" in result


# ---------------------------------------------------------------------------
# Relay: relay_message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_message_sends_to_recipient():
    """Mocks send_to_user, verifies it's called with correct recipient and attribution prefix."""
    conn = AsyncMock()
    # User lookup for recipient
    conn.fetchrow.side_effect = [
        {"id": "uuid-meral"},  # recipient exists
    ]

    pool = _make_mock_pool(conn)

    with (
        patch("app.tools.relay.get_pool", new_callable=AsyncMock) as get_pool,
        patch("app.tools.relay.send_to_user", new_callable=AsyncMock) as mock_send,
    ):
        get_pool.return_value = pool

        result = await relay_message(recipient="Meral", message="I'll be late", user="Ruben")
        assert result == "Message relayed to Meral."

        # Verify send_to_user was called with the right args
        mock_send.assert_called_once()
        call_args, call_kwargs = mock_send.call_args
        assert call_args[0] == "Meral"
        assert "📩 From Ruben:" in call_args[1]
        assert call_kwargs.get("proactive") is False  # proactive=False


@pytest.mark.asyncio
async def test_relay_message_sender_is_recipient():
    """Returns self-relay error, send_to_user not called."""
    conn = AsyncMock()

    pool = _make_mock_pool(conn)

    with (
        patch("app.tools.relay.get_pool", new_callable=AsyncMock) as get_pool,
        patch("app.tools.relay.send_to_user", new_callable=AsyncMock) as mock_send,
    ):
        get_pool.return_value = pool

        result = await relay_message(recipient="Ruben", message="Hi", user="Ruben")
        assert result == "You cannot relay a message to yourself."
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_relay_message_unknown_recipient():
    """User not in DB returns error, send_to_user not called."""
    conn = AsyncMock()
    conn.fetchrow.return_value = None  # recipient not found

    pool = _make_mock_pool(conn)

    with (
        patch("app.tools.relay.get_pool", new_callable=AsyncMock) as get_pool,
        patch("app.tools.relay.send_to_user", new_callable=AsyncMock) as mock_send,
    ):
        get_pool.return_value = pool

        result = await relay_message(recipient="Stranger", message="Hello", user="Ruben")
        assert result == "Could not find user 'Stranger'."
        mock_send.assert_not_called()
