"""Homechart API client."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)


@dataclass
class HomechartTask:
    """Represents a Homechart task."""

    id: str
    name: str
    details: str | None = None
    done: bool = False
    due_date: date | None = None
    assignees: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    color: int | None = None
    project_id: str | None = None
    project_name: str | None = None
    last_done_date: date | None = None
    recurrence: dict | None = None


@dataclass
class HomechartEvent:
    """Represents a Homechart calendar event."""

    id: str
    name: str
    details: str | None = None
    location: str | None = None
    date_start: date | None = None
    date_end: date | None = None
    time_start: str | None = None
    duration: int | None = None
    participants: list[str] = field(default_factory=list)
    color: int | None = None
    all_day: bool = True


@dataclass
class HomechartProject:
    """Represents a Homechart project."""

    id: str
    name: str
    color: int | None = None


@dataclass
class HomechartHouseholdMember:
    """Represents a household member."""

    id: str
    name: str
    email: str | None = None


class HomechartApiError(Exception):
    """Homechart API error."""


class HomechartAuthError(HomechartApiError):
    """Homechart authentication error."""


class HomechartApi:
    """Homechart API client."""

    def __init__(self, url: str, api_key: str) -> None:
        """Initialize the API client.
        
        api_key can be either:
        - Just the token/key: "019b4e1d-d630-79a9-bf23-49110cff029b"
        - Or id:key format: "019b4e1d-d630-79a4-9267-708fd080f79e:019b4e1d-d630-79a9-bf23-49110cff029b"
        """
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._session = requests.Session()
        
        # Parse if id:key format provided
        if ":" in api_key:
            session_id, session_key = api_key.split(":", 1)
        else:
            session_id = None
            session_key = api_key
        
        # Homechart uses cookie-based auth
        # The cookie format appears to be: homechart=<session_id>|<session_key>
        # Or possibly just the key
        if session_id:
            cookie_value = f"{session_id}|{session_key}"
            self._session.cookies.set("homechart", cookie_value, domain="web.homechart.app")
            self._session.cookies.set("homechart", cookie_value, domain="homechart.app")
        
        # Also try just the key in various formats
        self._session.cookies.set("homechart", session_key, domain="web.homechart.app")
        
        # Try Authorization header as well
        self._session.headers.update({
            "Authorization": f"Bearer {session_key}",
            "x-homechart-key": session_key,
        })
        
        if session_id:
            self._session.headers["x-homechart-id"] = session_id

    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Make an API request."""
        url = f"{self._url}/api/v1{endpoint}"

        try:
            response = self._session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=30,
            )
        except requests.RequestException as err:
            raise HomechartApiError(f"Request failed: {err}") from err

        if response.status_code == 401:
            raise HomechartAuthError("Invalid API key")

        if response.status_code == 403:
            raise HomechartAuthError("Access denied")

        if not response.ok:
            raise HomechartApiError(
                f"API error: {response.status_code} - {response.text}"
            )

        try:
            return response.json()
        except ValueError:
            return {}

    def test_connection(self) -> bool:
        """Test the API connection."""
        try:
            self._request("GET", "/auth/accounts")
            return True
        except HomechartApiError:
            return False

    def get_household_members(self) -> list[HomechartHouseholdMember]:
        """Get household members."""
        data = self._request("GET", "/auth/households")
        members = []

        if isinstance(data, dict) and "dataValue" in data:
            households = data.get("dataValue", [])
            if households:
                # Get members from the first (primary) household
                for household in households:
                    member_list = household.get("members", [])
                    for member in member_list:
                        # Use 'id' field - this matches what's used in task assignees
                        # Also try authAccountID as fallback
                        member_id = member.get("id") or member.get("authAccountID", "")
                        _LOGGER.debug(
                            "Found member: %s with id=%s, authAccountID=%s",
                            member.get("name"),
                            member.get("id"),
                            member.get("authAccountID"),
                        )
                        members.append(
                            HomechartHouseholdMember(
                                id=member_id,
                                name=member.get("name", "Unknown"),
                                email=member.get("emailAddress"),
                            )
                        )

        return members

    def get_projects(self) -> list[HomechartProject]:
        """Get all projects."""
        data = self._request("GET", "/plan/projects")
        projects = []

        if isinstance(data, dict) and "dataValue" in data:
            for item in data.get("dataValue", []):
                projects.append(
                    HomechartProject(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        color=item.get("color"),
                    )
                )

        return projects

    def get_tasks(self) -> list[HomechartTask]:
        """Get all tasks."""
        data = self._request("GET", "/plan/tasks")
        tasks = []

        # Get projects for name lookup
        projects = {p.id: p.name for p in self.get_projects()}

        if isinstance(data, dict) and "dataValue" in data:
            for item in data.get("dataValue", []):
                due_date = None
                if item.get("dueDate"):
                    try:
                        due_date = datetime.fromisoformat(
                            item["dueDate"].replace("Z", "+00:00")
                        ).date()
                    except (ValueError, TypeError):
                        pass

                last_done = None
                if item.get("lastDoneDate"):
                    try:
                        last_done = datetime.fromisoformat(
                            str(item["lastDoneDate"]).replace("Z", "+00:00")
                        ).date()
                    except (ValueError, TypeError):
                        pass

                project_id = item.get("planProjectID")
                
                # Try both 'assignees' and 'participants' - Homechart might use either
                assignees = item.get("assignees", []) or []
                if not assignees:
                    assignees = item.get("participants", []) or []
                
                # Also try authHouseholdMembers or similar variations
                if not assignees:
                    assignees = item.get("authHouseholdMembers", []) or []
                
                # Debug log to see what's in the raw item
                _LOGGER.debug(
                    "Task '%s' raw data keys: %s",
                    item.get("name"),
                    list(item.keys()),
                )
                _LOGGER.debug(
                    "Task '%s' assignees=%s, participants=%s",
                    item.get("name"),
                    item.get("assignees"),
                    item.get("participants"),
                )

                tasks.append(
                    HomechartTask(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        details=item.get("details"),
                        done=item.get("done", False),
                        due_date=due_date,
                        assignees=assignees,
                        tags=item.get("tags", []) or [],
                        color=item.get("color"),
                        project_id=project_id,
                        project_name=projects.get(project_id) if project_id else None,
                        last_done_date=last_done,
                        recurrence=item.get("recurrence"),
                    )
                )

        return tasks

    def get_tasks_due_today(self) -> list[HomechartTask]:
        """Get tasks due today."""
        today = date.today()
        return [
            t
            for t in self.get_tasks()
            if t.due_date == today and not t.done
        ]

    def get_tasks_overdue(self) -> list[HomechartTask]:
        """Get overdue tasks."""
        today = date.today()
        return [
            t
            for t in self.get_tasks()
            if t.due_date and t.due_date < today and not t.done
        ]

    def get_tasks_upcoming(self, days: int = 7) -> list[HomechartTask]:
        """Get upcoming tasks within the specified number of days."""
        today = date.today()
        end_date = today + timedelta(days=days)
        return [
            t
            for t in self.get_tasks()
            if t.due_date and today <= t.due_date <= end_date and not t.done
        ]

    def create_task(
        self,
        name: str,
        due_date: date | None = None,
        details: str | None = None,
        project_id: str | None = None,
        assignees: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> HomechartTask:
        """Create a new task."""
        payload: dict[str, Any] = {"name": name}

        if due_date:
            payload["dueDate"] = due_date.isoformat()
        if details:
            payload["details"] = details
        if project_id:
            payload["planProjectID"] = project_id
        if assignees:
            payload["assignees"] = assignees
        if tags:
            payload["tags"] = tags

        data = self._request("POST", "/plan/tasks", data=payload)

        # Parse and return the created task
        task_data = data.get("dataValue", [{}])[0] if data.get("dataValue") else {}
        return HomechartTask(
            id=task_data.get("id", ""),
            name=task_data.get("name", name),
            details=details,
            due_date=due_date,
            assignees=assignees or [],
            tags=tags or [],
            project_id=project_id,
        )

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as complete."""
        try:
            # Get the current task first
            tasks = self.get_tasks()
            task = next((t for t in tasks if t.id == task_id), None)

            if not task:
                _LOGGER.error("Task not found: %s", task_id)
                return False

            # Update the task to mark as done
            payload = {
                "id": task_id,
                "name": task.name,
                "done": True,
            }

            self._request("PUT", f"/plan/tasks/{task_id}", data=payload)
            return True
        except HomechartApiError as err:
            _LOGGER.error("Failed to complete task: %s", err)
            return False

    def uncomplete_task(self, task_id: str) -> bool:
        """Mark a task as incomplete."""
        try:
            tasks = self.get_tasks()
            task = next((t for t in tasks if t.id == task_id), None)

            if not task:
                _LOGGER.error("Task not found: %s", task_id)
                return False

            payload = {
                "id": task_id,
                "name": task.name,
                "done": False,
            }

            self._request("PUT", f"/plan/tasks/{task_id}", data=payload)
            return True
        except HomechartApiError as err:
            _LOGGER.error("Failed to uncomplete task: %s", err)
            return False

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        try:
            self._request("DELETE", f"/plan/tasks/{task_id}")
            return True
        except HomechartApiError as err:
            _LOGGER.error("Failed to delete task: %s", err)
            return False

    def get_events(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[HomechartEvent]:
        """Get calendar events."""
        data = self._request("GET", "/calendar/events")
        events = []

        if isinstance(data, dict) and "dataValue" in data:
            for item in data.get("dataValue", []):
                event_start = None
                event_end = None

                if item.get("dateStart"):
                    try:
                        event_start = datetime.fromisoformat(
                            item["dateStart"].replace("Z", "+00:00")
                        ).date()
                    except (ValueError, TypeError):
                        pass

                if item.get("dateEnd"):
                    try:
                        event_end = datetime.fromisoformat(
                            item["dateEnd"].replace("Z", "+00:00")
                        ).date()
                    except (ValueError, TypeError):
                        pass

                # Filter by date range if provided
                if start_date and event_start and event_start < start_date:
                    continue
                if end_date and event_start and event_start > end_date:
                    continue

                events.append(
                    HomechartEvent(
                        id=item.get("id", ""),
                        name=item.get("name", ""),
                        details=item.get("details"),
                        location=item.get("location"),
                        date_start=event_start,
                        date_end=event_end,
                        time_start=item.get("timeStart"),
                        duration=item.get("duration"),
                        participants=item.get("participants", []) or [],
                        color=item.get("color"),
                        all_day=not bool(item.get("timeStart")),
                    )
                )

        return events

    def create_event(
        self,
        name: str,
        date_start: date,
        date_end: date | None = None,
        time_start: str | None = None,
        duration: int | None = None,
        details: str | None = None,
        location: str | None = None,
        participants: list[str] | None = None,
    ) -> HomechartEvent:
        """Create a calendar event."""
        payload: dict[str, Any] = {
            "name": name,
            "dateStart": date_start.isoformat(),
        }

        if date_end:
            payload["dateEnd"] = date_end.isoformat()
        if time_start:
            payload["timeStart"] = time_start
        if duration:
            payload["duration"] = duration
        if details:
            payload["details"] = details
        if location:
            payload["location"] = location
        if participants:
            payload["participants"] = participants

        data = self._request("POST", "/calendar/events", data=payload)

        event_data = data.get("dataValue", [{}])[0] if data.get("dataValue") else {}
        return HomechartEvent(
            id=event_data.get("id", ""),
            name=event_data.get("name", name),
            details=details,
            location=location,
            date_start=date_start,
            date_end=date_end,
            time_start=time_start,
            duration=duration,
            participants=participants or [],
            all_day=not bool(time_start),
        )

    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event."""
        try:
            self._request("DELETE", f"/calendar/events/{event_id}")
            return True
        except HomechartApiError as err:
            _LOGGER.error("Failed to delete event: %s", err)
            return False
