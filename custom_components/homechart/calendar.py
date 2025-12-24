"""Calendar platform for Homechart integration."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import HomechartEvent
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart calendar."""
    event_coordinator = hass.data[DOMAIN][entry.entry_id]["event_coordinator"]
    task_coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]

    entities = [
        HomechartCalendar(event_coordinator, task_coordinator, entry),
    ]

    async_add_entities(entities)


class HomechartCalendar(CoordinatorEntity, CalendarEntity):
    """Representation of a Homechart calendar."""

    _attr_has_entity_name = True
    _attr_name = "Calendar"

    def __init__(
        self,
        event_coordinator,
        task_coordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the calendar."""
        super().__init__(event_coordinator)
        self._task_coordinator = task_coordinator
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._entry = entry

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        events = self._get_all_calendar_events()
        now = dt_util.now()
        today = now.date()

        # Filter to current/upcoming events
        upcoming = []
        for event in events:
            # Handle both date and datetime objects
            event_end = event.end
            event_start = event.start
            
            # Convert date to datetime for comparison if needed
            if isinstance(event_end, date) and not isinstance(event_end, datetime):
                # All-day event - compare dates
                if event_end >= today:
                    upcoming.append(event)
            elif event_end and event_end > now:
                upcoming.append(event)
            elif event_start:
                # Check start date as fallback
                if isinstance(event_start, date) and not isinstance(event_start, datetime):
                    if event_start >= today:
                        upcoming.append(event)
                elif event_start >= now:
                    upcoming.append(event)

        if not upcoming:
            return None

        # Sort by start time
        def sort_key(e):
            if isinstance(e.start, datetime):
                return e.start
            elif isinstance(e.start, date):
                return datetime.combine(e.start, datetime.min.time(), tzinfo=now.tzinfo)
            return datetime.max.replace(tzinfo=now.tzinfo)
        
        upcoming.sort(key=sort_key)
        return upcoming[0] if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = self._get_all_calendar_events()
        start_d = start_date.date() if isinstance(start_date, datetime) else start_date
        end_d = end_date.date() if isinstance(end_date, datetime) else end_date

        # Filter by date range
        filtered = []
        for event in events:
            event_start = event.start
            event_end = event.end
            
            # Normalize to dates for comparison
            if isinstance(event_start, datetime):
                ev_start_d = event_start.date()
            elif isinstance(event_start, date):
                ev_start_d = event_start
            else:
                continue
                
            if isinstance(event_end, datetime):
                ev_end_d = event_end.date()
            elif isinstance(event_end, date):
                ev_end_d = event_end
            else:
                ev_end_d = ev_start_d
            
            # Check if event overlaps with requested range
            if ev_start_d <= end_d and ev_end_d >= start_d:
                filtered.append(event)

        return filtered

    def _get_all_calendar_events(self) -> list[CalendarEvent]:
        """Get all calendar events including tasks with due dates."""
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()

        # Add Homechart events
        if self.coordinator.data:
            for hc_event in self.coordinator.data.get("events", []):
                cal_event = self._convert_homechart_event(hc_event, tz)
                if cal_event:
                    events.append(cal_event)

        # Add tasks with due dates as all-day events
        if self._task_coordinator.data:
            for task in self._task_coordinator.data.get("tasks", []):
                if task.due_date and not task.done:
                    events.append(
                        CalendarEvent(
                            summary=f"📋 {task.name}",
                            start=task.due_date,
                            end=task.due_date + timedelta(days=1),
                            description=task.details,
                            uid=f"task_{task.id}",
                        )
                    )

        return events

    def _convert_homechart_event(
        self, hc_event: HomechartEvent, tz
    ) -> CalendarEvent | None:
        """Convert a Homechart event to a CalendarEvent."""
        if not hc_event.date_start:
            return None

        start: datetime | date
        end: datetime | date

        if hc_event.time_start and hc_event.duration:
            # Timed event
            try:
                # Parse time (HH:MM format)
                hours, minutes = map(int, hc_event.time_start.split(":"))
                start = datetime.combine(
                    hc_event.date_start,
                    datetime.min.time().replace(hour=hours, minute=minutes),
                    tzinfo=tz,
                )
                end = start + timedelta(minutes=hc_event.duration)
            except (ValueError, TypeError):
                # Fall back to all-day
                start = hc_event.date_start
                end = (hc_event.date_end or hc_event.date_start) + timedelta(days=1)
        else:
            # All-day event
            start = hc_event.date_start
            end = (hc_event.date_end or hc_event.date_start) + timedelta(days=1)

        return CalendarEvent(
            summary=hc_event.name,
            start=start,
            end=end,
            description=hc_event.details,
            location=hc_event.location,
            uid=f"event_{hc_event.id}",
        )
