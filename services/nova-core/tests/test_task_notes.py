"""Tests for the task_notes tool (Phase 45)."""
from __future__ import annotations

import uuid as _uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tools.task_notes import add_task_note, list_task_notes, delete_task_note

_TASK_ID = "00000000-0000-0000-0000-000000000001"
_NOTE_ID = "00000000-0000-0000-0000-000000000010"


def _make_mock_pool(mock_conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = mock_conn
    return pool


@pytest.mark.asyncio
async def test_add_task_note_success():
    conn = AsyncMock()
    conn.fetchval.side_effect = [_uuid.UUID(_TASK_ID), _uuid.UUID(_NOTE_ID)]
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task_note(_TASK_ID, "Buy organic milk", user="Ruben")
        assert "Note added" in result
        assert _TASK_ID in result


@pytest.mark.asyncio
async def test_add_task_note_empty_content():
    result = await add_task_note(_TASK_ID, "", user="Ruben")
    assert "cannot be empty" in result


@pytest.mark.asyncio
async def test_add_task_note_invalid_uuid():
    result = await add_task_note("bad-uuid", "note content", user="Ruben")
    assert "Invalid" in result


@pytest.mark.asyncio
async def test_add_task_note_no_active_task():
    conn = AsyncMock()
    conn.fetchval.return_value = None
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await add_task_note(_TASK_ID, "some note", user="Ruben")
        assert "No active task" in result


@pytest.mark.asyncio
async def test_list_task_notes():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {"id": _NOTE_ID, "content": "First note", "created_at": None, "author": "Ruben"},
    ]
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_task_notes(_TASK_ID)
        assert "Notes for task" in result
        assert "First note" in result


@pytest.mark.asyncio
async def test_list_task_notes_empty():
    conn = AsyncMock()
    conn.fetch.return_value = []
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await list_task_notes(_TASK_ID)
        assert "No notes for task" in result


@pytest.mark.asyncio
async def test_delete_task_note_success():
    conn = AsyncMock()
    conn.execute.return_value = "DELETE 1"
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await delete_task_note(_NOTE_ID)
        assert "deleted" in result


@pytest.mark.asyncio
async def test_delete_task_note_not_found():
    conn = AsyncMock()
    conn.execute.return_value = "DELETE 0"
    pool = _make_mock_pool(conn)

    with patch("app.tools.task_notes.get_pool", new_callable=AsyncMock) as get_pool:
        get_pool.return_value = pool

        result = await delete_task_note(_NOTE_ID)
        assert "No note found" in result
