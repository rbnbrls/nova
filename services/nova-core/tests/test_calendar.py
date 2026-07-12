"""Tests for the calendar tool (CalDAV-backed).

Covers CAL-01 through CAL-03: event creation, querying, timezone
handling, and recurring-event expansion.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.tools.calendar import create_event, list_events


def _make_caldav_mocks() -> tuple[MagicMock, MagicMock]:
    """Set up mock CalDAV client chain and return (client, calendar)."""
    mock_client = MagicMock()
    mock_principal = MagicMock()
    mock_calendar = MagicMock()

    mock_client.principal.return_value = mock_principal
    mock_principal.calendars.return_value = [mock_calendar]

    return mock_client, mock_calendar


def _make_mock_event(
    summary: str,
    dtstart: datetime,
    dtend: datetime,
    location: str | None = None,
) -> MagicMock:
    """Build a mock caldav Event with a vobject_instance containing a VEVENT."""
    mock_vevent = MagicMock()
    mock_vevent.summary.value = summary
    mock_vevent.dtstart.value = dtstart
    mock_vevent.dtend.value = dtend
    # Always set location.value so ``hasattr`` + truthiness works predictably
    mock_vevent.location.value = location or ""

    mock_vobject = MagicMock()
    mock_vobject.vevent = mock_vevent

    return MagicMock(vobject_instance=mock_vobject)


# ---------------------------------------------------------------------------
# CAL-01 : Create event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_event_basic():
    """CAL-01: A calendar event with valid ISO dates is created successfully."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await create_event(
            "Dentist appointment",
            "2026-07-15T10:00:00",
            "2026-07-15T11:00:00",
        )
        assert result == "Created event 'Dentist appointment' 2026-07-15T10:00:00\u20132026-07-15T11:00:00."
        mock_calendar.save_event.assert_called_once()


@pytest.mark.asyncio
async def test_create_event_with_location():
    """CAL-01: An event with an optional location includes it in the response."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await create_event(
            "Team standup",
            "2026-07-16T09:00:00",
            "2026-07-16T09:30:00",
            location="Room 3.2",
        )
        assert " @ Room 3.2" in result
        mock_calendar.save_event.assert_called_once()


@pytest.mark.asyncio
async def test_create_event_rejects_invalid_date():
    """CAL-01: Non-parseable date strings return an error."""
    mock_client, _mock_calendar = _make_caldav_mocks()

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await create_event(
            "Bad date",
            "next Thursday",
            "next Friday",
        )
        assert "Error: Invalid date format" in result


# ---------------------------------------------------------------------------
# CAL-02 : Query events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_events_in_date_range():
    """CAL-02: Listing events in a range returns formatted event details."""
    mock_client, mock_calendar = _make_caldav_mocks()

    mock_calendar.search.return_value = [
        _make_mock_event(
            "Dentist",
            datetime(2026, 7, 15, 10, 0, 0),
            datetime(2026, 7, 15, 11, 0, 0),
            location="Clinic",
        ),
        _make_mock_event(
            "Lunch",
            datetime(2026, 7, 15, 12, 0, 0),
            datetime(2026, 7, 15, 13, 0, 0),
        ),
    ]

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await list_events("2026-07-15T00:00:00", "2026-07-15T23:59:59")
        assert "Dentist" in result
        assert "Lunch" in result
        assert "Clinic" in result
        # Verify expand=True was passed for recurring-event expansion
        mock_calendar.search.assert_called_once_with(
            start=datetime(2026, 7, 15, 0, 0, 0),
            end=datetime(2026, 7, 15, 23, 59, 59),
            event=True,
            expand=True,
        )


@pytest.mark.asyncio
async def test_list_events_empty_range():
    """CAL-02: A range with no events returns a friendly empty message."""
    mock_client, mock_calendar = _make_caldav_mocks()
    mock_calendar.search.return_value = []

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await list_events("2026-07-15T00:00:00", "2026-07-16T00:00:00")
        assert "No events between" in result


# ---------------------------------------------------------------------------
# CAL-03 : Timezone & recurring events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_events_with_explicit_timezone_offset():
    """CAL-03: An ISO 8601 timestamp with explicit UTC offset is parsed correctly."""
    mock_client, mock_calendar = _make_caldav_mocks()
    mock_calendar.search.return_value = [
        _make_mock_event(
            "Event with offset",
            datetime(2026, 7, 15, 8, 0, 0),  # 10:00 CEST = 08:00 UTC
            datetime(2026, 7, 15, 9, 0, 0),
        ),
    ]

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await list_events(
            "2026-07-15T10:00:00+02:00", "2026-07-15T11:00:00+02:00"
        )
        assert "Event with offset" in result
        # The search should have been called with the parsed datetime objects
        call_kwargs = mock_calendar.search.call_args[1]
        assert call_kwargs["start"].tzinfo is not None  # tz-aware


@pytest.mark.asyncio
async def test_list_events_expands_recurring():
    """CAL-03: The search call passes expand=True so recurring events are expanded."""
    mock_client, mock_calendar = _make_caldav_mocks()
    mock_calendar.search.return_value = [
        _make_mock_event(
            "Weekly standup (recurring)",
            datetime(2026, 7, 15, 9, 0, 0),
            datetime(2026, 7, 15, 9, 30, 0),
        ),
    ]

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        await list_events("2026-07-15T00:00:00", "2026-07-15T23:59:59")
        assert mock_calendar.search.call_args[1].get("expand") is True


@pytest.mark.asyncio
async def test_create_event_with_z_suffix():
    """CAL-03: The Z suffix (UTC) is correctly replaced with +00:00 before parsing."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch(
        "app.tools.calendar.caldav.DAVClient", return_value=mock_client
    ):
        result = await create_event(
            "Global meeting",
            "2026-07-20T14:00:00Z",
            "2026-07-20T15:00:00Z",
        )
        assert "Created event" in result
        mock_calendar.save_event.assert_called_once()
