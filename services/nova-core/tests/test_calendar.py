"""Tests for the calendar tool (CalDAV-backed).

Covers CAL-01 through CAL-03: event creation, querying, timezone
handling, and recurring-event expansion.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from icalendar import Calendar as iCalendar

from app.tools.calendar import create_event, list_events

TZ = ZoneInfo("Europe/Amsterdam")


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
        mock_calendar.search.assert_called_once()
        call_kwargs = mock_calendar.search.call_args[1]
        assert call_kwargs["start"] == datetime(2026, 7, 15, 0, 0, 0, tzinfo=TZ)
        assert call_kwargs["end"] == datetime(2026, 7, 15, 23, 59, 59, tzinfo=TZ)
        assert call_kwargs["event"] is True
        assert call_kwargs["expand"] is True


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


# ---------------------------------------------------------------------------
# Phase 5 additions: description, timezone normalization, RRULE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_event_with_description():
    """Event with description includes it in response and VEVENT."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        result = await create_event(
            "Birthday party", "2026-08-01T18:00:00", "2026-08-01T23:00:00",
            description="Bring gifts",
        )
        assert "Bring gifts" in result
        mock_calendar.save_event.assert_called_once()


@pytest.mark.asyncio
async def test_create_event_normalizes_naive_timestamp():
    """Naive timestamps get household timezone assigned."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        await create_event("Test", "2026-07-15T10:00:00", "2026-07-15T11:00:00")
        saved_ical = mock_calendar.save_event.call_args[0][0]
        parsed = iCalendar.from_ical(saved_ical)
        vevent = parsed.walk("VEVENT")[0]
        dtstart = vevent["dtstart"].dt
        assert dtstart.tzinfo is not None


@pytest.mark.asyncio
async def test_create_event_offset_timestamps_unchanged():
    """Timestamps with explicit offset are accepted correctly."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        result = await create_event("Test offset", "2026-07-15T10:00:00+02:00", "2026-07-15T11:00:00+02:00")
        assert "Created event" in result
        mock_calendar.save_event.assert_called_once()


@pytest.mark.asyncio
async def test_list_events_normalizes_naive_timestamp():
    """list_events normalizes naive timestamps before passing to search."""
    mock_client, mock_calendar = _make_caldav_mocks()
    mock_calendar.search.return_value = []

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        await list_events("2026-07-15T00:00:00", "2026-07-15T23:59:59")
        call_kwargs = mock_calendar.search.call_args[1]
        assert call_kwargs["start"].tzinfo is not None


@pytest.mark.asyncio
async def test_create_event_with_rrule():
    """RRULE parameter creates a VEVENT with RRULE property."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        await create_event(
            "Standup", "2026-07-15T09:00:00", "2026-07-15T09:30:00",
            rrule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
        )
        saved_ical = mock_calendar.save_event.call_args[0][0]
        parsed = iCalendar.from_ical(saved_ical)
        vevent = parsed.walk("VEVENT")[0]
        assert "RRULE" in vevent


@pytest.mark.asyncio
async def test_create_event_without_rrule_no_recurrence():
    """No RRULE parameter means no RRULE in VEVENT."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        await create_event("Single meeting", "2026-07-15T14:00:00", "2026-07-15T15:00:00")
        saved_ical = mock_calendar.save_event.call_args[0][0]
        parsed = iCalendar.from_ical(saved_ical)
        vevent = parsed.walk("VEVENT")[0]
        assert "RRULE" not in vevent


@pytest.mark.asyncio
async def test_create_event_invalid_rrule_still_saves():
    """An unusual RRULE string still saves (icalendar accepts it)."""
    mock_client, mock_calendar = _make_caldav_mocks()

    with patch("app.tools.calendar.caldav.DAVClient", return_value=mock_client):
        result = await create_event(
            "Bad rrule", "2026-07-15T10:00:00", "2026-07-15T11:00:00",
            rrule="NOT A VALID RRULE",
        )
        assert "Created event" in result
        mock_calendar.save_event.assert_called_once()
