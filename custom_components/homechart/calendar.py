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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import HomechartEvent, HomechartHouseholdMember
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart calendar."""
    event_coordinator = hass.data[DOMAIN][entry.entry_id]["event_coordinator"]
    task_coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]
    members = hass.data[DOMAIN][entry.entry_id]["members"]

    entities = [
        # Household calendar (all events/tasks)
        HomechartHouseholdCalendar(event_coordinator, task_coordinator, entry),
    ]

    # Per-member calendars
    for member in members:
        entities.append(
            HomechartMemberCalendar(event_coordinator, task_coordinator, entry, member)
        )

    async_add_entities(entities)


class HomechartHouseholdCalendar(CoordinatorEntity, CalendarEntity):
    """Household calendar showing all events/tasks."""

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
        self._attr_unique_id = f"{entry.entry_id}_household_calendar"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_household")},
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        events = self._get_all_calendar_events()
        now = dt_util.now()
        today = now.date()

        upcoming = []
        for event in events:
            event_end = event.end
            event_start = event.start
            
            if isinstance(event_end, date) and not isinstance(event_end, datetime):
                if event_end >= today:
                    upcoming.append(event)
            elif event_end and event_end > now:
                upcoming.append(event)
            elif event_start:
                if isinstance(event_start, date) and not isinstance(event_start, datetime):
                    if event_start >= today:
                        upcoming.append(event)
                elif event_start >= now:
                    upcoming.append(event)

        if not upcoming:
            return None

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

        filtered = []
        for event in events:
            event_start = event.start
            event_end = event.end
            
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
            
            if ev_start_d <= end_d and ev_end_d >= start_d:
                filtered.append(event)

        return filtered

    def _get_all_calendar_events(self) -> list[CalendarEvent]:
        """Get all calendar events including tasks with due dates."""
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()

        if self.coordinator.data:
            for hc_event in self.coordinator.data.get("events", []):
                # Expand recurring events
                expanded_events = self._expand_recurring_event(hc_event, tz)
                events.extend(expanded_events)

        if self._task_coordinator.data:
            for task in self._task_coordinator.data.get("tasks", []):
                if task.due_date and not task.done:
                    # Include assignee names in task title
                    member_map = self._task_coordinator.data.get("member_map", {})
                    assignee_names = []
                    for aid in (task.assignees or []):
                        member = member_map.get(aid)
                        if member:
                            assignee_names.append(member.name)
                    
                    title = f"📋 {task.name}"
                    if assignee_names:
                        title += f" ({', '.join(assignee_names)})"
                    
                    events.append(
                        CalendarEvent(
                            summary=title,
                            start=task.due_date,
                            end=task.due_date + timedelta(days=1),
                            description=task.details,
                            uid=f"task_{task.id}",
                        )
                    )

        return events

    def _expand_recurring_event(
        self, hc_event: HomechartEvent, tz
    ) -> list[CalendarEvent]:
        """Expand a recurring event into multiple calendar events."""
        if not hc_event.date_start:
            return []

        # If no recurrence, just convert normally
        if not hc_event.recurrence:
            cal_event = self._convert_homechart_event(hc_event, tz)
            return [cal_event] if cal_event else []

        recurrence = hc_event.recurrence
        separation = recurrence.get("separation", 0)
        
        # If separation is 0, no real recurrence
        if not separation:
            cal_event = self._convert_homechart_event(hc_event, tz)
            return [cal_event] if cal_event else []

        events = []
        today = date.today()
        
        # Generate events from start date up to 90 days in future
        start_window = today - timedelta(days=30)  # Show past 30 days
        end_window = today + timedelta(days=90)    # Show future 90 days
        
        # Parse recurrence end date if set
        recurrence_end = None
        if recurrence.get("end"):
            try:
                recurrence_end = date.fromisoformat(str(recurrence["end"]))
            except (ValueError, TypeError):
                pass

        # Get skip days from the event
        skip_days = set(hc_event.skip_days or [])

        # Generate occurrences
        current_date = hc_event.date_start
        max_occurrences = 365  # Safety limit
        count = 0
        
        while count < max_occurrences:
            # Stop if past end window
            if current_date > end_window:
                break
            
            # Stop if past recurrence end
            if recurrence_end and current_date > recurrence_end:
                break
            
            # Only add if within window and not skipped
            if current_date >= start_window and current_date not in skip_days:
                cal_event = self._convert_homechart_event_on_date(
                    hc_event, current_date, tz
                )
                if cal_event:
                    events.append(cal_event)
            
            # Move to next occurrence
            current_date = current_date + timedelta(days=separation)
            count += 1

        return events

    def _convert_homechart_event_on_date(
        self, hc_event: HomechartEvent, event_date: date, tz
    ) -> CalendarEvent | None:
        """Convert a Homechart event to a CalendarEvent on a specific date."""
        start: datetime | date
        end: datetime | date

        if hc_event.time_start and hc_event.duration:
            try:
                hours, minutes = map(int, hc_event.time_start.split(":"))
                start = datetime.combine(
                    event_date,
                    datetime.min.time().replace(hour=hours, minute=minutes),
                    tzinfo=tz,
                )
                end = start + timedelta(minutes=hc_event.duration)
            except (ValueError, TypeError):
                start = event_date
                end = event_date + timedelta(days=1)
        else:
            start = event_date
            end = event_date + timedelta(days=1)

        # Include participant names
        member_map = self.coordinator.data.get("member_map", {})
        participant_names = []
        for pid in (hc_event.participants or []):
            member = member_map.get(pid)
            if member:
                participant_names.append(member.name)

        summary = hc_event.name
        if participant_names:
            summary += f" ({', '.join(participant_names)})"

        return CalendarEvent(
            summary=summary,
            start=start,
            end=end,
            description=hc_event.details,
            location=hc_event.location,
            uid=f"event_{hc_event.id}_{event_date.isoformat()}",
        )

    def _convert_homechart_event(
        self, hc_event: HomechartEvent, tz
    ) -> CalendarEvent | None:
        """Convert a Homechart event to a CalendarEvent."""
        if not hc_event.date_start:
            return None

        start: datetime | date
        end: datetime | date

        if hc_event.time_start and hc_event.duration:
            try:
                hours, minutes = map(int, hc_event.time_start.split(":"))
                start = datetime.combine(
                    hc_event.date_start,
                    datetime.min.time().replace(hour=hours, minute=minutes),
                    tzinfo=tz,
                )
                end = start + timedelta(minutes=hc_event.duration)
            except (ValueError, TypeError):
                start = hc_event.date_start
                end = (hc_event.date_end or hc_event.date_start) + timedelta(days=1)
        else:
            start = hc_event.date_start
            end = (hc_event.date_end or hc_event.date_start) + timedelta(days=1)

        # Include participant names
        member_map = self.coordinator.data.get("member_map", {})
        participant_names = []
        for pid in (hc_event.participants or []):
            member = member_map.get(pid)
            if member:
                participant_names.append(member.name)

        summary = hc_event.name
        if participant_names:
            summary += f" ({', '.join(participant_names)})"

        return CalendarEvent(
            summary=summary,
            start=start,
            end=end,
            description=hc_event.details,
            location=hc_event.location,
            uid=f"event_{hc_event.id}",
        )


class HomechartMemberCalendar(CoordinatorEntity, CalendarEntity):
    """Per-member calendar showing only their events/tasks."""

    _attr_has_entity_name = True

    def __init__(
        self,
        event_coordinator,
        task_coordinator,
        entry: ConfigEntry,
        member: HomechartHouseholdMember,
    ) -> None:
        """Initialize the calendar."""
        super().__init__(event_coordinator)
        self._task_coordinator = task_coordinator
        self._member = member
        self._attr_unique_id = f"{entry.entry_id}_{member.id}_calendar"
        self._attr_name = "Calendar"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._member.id}")},
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event for this member."""
        events = self._get_member_calendar_events()
        now = dt_util.now()
        today = now.date()

        upcoming = []
        for event in events:
            event_end = event.end
            event_start = event.start
            
            if isinstance(event_end, date) and not isinstance(event_end, datetime):
                if event_end >= today:
                    upcoming.append(event)
            elif event_end and event_end > now:
                upcoming.append(event)
            elif event_start:
                if isinstance(event_start, date) and not isinstance(event_start, datetime):
                    if event_start >= today:
                        upcoming.append(event)
                elif event_start >= now:
                    upcoming.append(event)

        if not upcoming:
            return None

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
        """Return calendar events for this member within a datetime range."""
        events = self._get_member_calendar_events()
        start_d = start_date.date() if isinstance(start_date, datetime) else start_date
        end_d = end_date.date() if isinstance(end_date, datetime) else end_date

        filtered = []
        for event in events:
            event_start = event.start
            event_end = event.end
            
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
            
            if ev_start_d <= end_d and ev_end_d >= start_d:
                filtered.append(event)

        return filtered

    def _get_member_calendar_events(self) -> list[CalendarEvent]:
        """Get calendar events for this member only."""
        events: list[CalendarEvent] = []
        tz = dt_util.get_default_time_zone()

        # Events where this member is a participant
        if self.coordinator.data:
            for hc_event in self.coordinator.data.get("events", []):
                if self._member.id in (hc_event.participants or []):
                    # Expand recurring events
                    expanded_events = self._expand_recurring_event(hc_event, tz)
                    events.extend(expanded_events)

        # Tasks assigned to this member
        if self._task_coordinator.data:
            for task in self._task_coordinator.data.get("tasks", []):
                if task.due_date and not task.done:
                    if self._member.id in (task.assignees or []):
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

    def _expand_recurring_event(
        self, hc_event: HomechartEvent, tz
    ) -> list[CalendarEvent]:
        """Expand a recurring event into multiple calendar events."""
        if not hc_event.date_start:
            return []

        # If no recurrence, just convert normally
        if not hc_event.recurrence:
            cal_event = self._convert_homechart_event_on_date(hc_event, hc_event.date_start, tz)
            return [cal_event] if cal_event else []

        recurrence = hc_event.recurrence
        separation = recurrence.get("separation", 0)
        
        # If separation is 0, no real recurrence
        if not separation:
            cal_event = self._convert_homechart_event_on_date(hc_event, hc_event.date_start, tz)
            return [cal_event] if cal_event else []

        events = []
        today = date.today()
        
        # Generate events from start date up to 90 days in future
        start_window = today - timedelta(days=30)
        end_window = today + timedelta(days=90)
        
        # Parse recurrence end date if set
        recurrence_end = None
        if recurrence.get("end"):
            try:
                recurrence_end = date.fromisoformat(str(recurrence["end"]))
            except (ValueError, TypeError):
                pass

        # Get skip days from the event
        skip_days = set(hc_event.skip_days or [])

        # Generate occurrences
        current_date = hc_event.date_start
        max_occurrences = 365
        count = 0
        
        while count < max_occurrences:
            if current_date > end_window:
                break
            if recurrence_end and current_date > recurrence_end:
                break
            
            if current_date >= start_window and current_date not in skip_days:
                cal_event = self._convert_homechart_event_on_date(
                    hc_event, current_date, tz
                )
                if cal_event:
                    events.append(cal_event)
            
            current_date = current_date + timedelta(days=separation)
            count += 1

        return events

    def _convert_homechart_event_on_date(
        self, hc_event: HomechartEvent, event_date: date, tz
    ) -> CalendarEvent | None:
        """Convert a Homechart event to a CalendarEvent on a specific date."""
        start: datetime | date
        end: datetime | date

        if hc_event.time_start and hc_event.duration:
            try:
                hours, minutes = map(int, hc_event.time_start.split(":"))
                start = datetime.combine(
                    event_date,
                    datetime.min.time().replace(hour=hours, minute=minutes),
                    tzinfo=tz,
                )
                end = start + timedelta(minutes=hc_event.duration)
            except (ValueError, TypeError):
                start = event_date
                end = event_date + timedelta(days=1)
        else:
            start = event_date
            end = event_date + timedelta(days=1)

        return CalendarEvent(
            summary=hc_event.name,
            start=start,
            end=end,
            description=hc_event.details,
            location=hc_event.location,
            uid=f"event_{hc_event.id}_{event_date.isoformat()}",
        )
