"""Sensor platform for Homechart integration."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HomechartHouseholdMember
from .const import (
    ATTR_COUNT,
    ATTR_TASKS,
    DOMAIN,
    SENSOR_TASKS_OVERDUE,
    SENSOR_TASKS_TODAY,
    SENSOR_TASKS_UPCOMING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]
    members = hass.data[DOMAIN][entry.entry_id]["members"]

    entities = []

    # Household-level sensors
    for sensor_type in [SENSOR_TASKS_TODAY, SENSOR_TASKS_OVERDUE, SENSOR_TASKS_UPCOMING]:
        entities.append(
            HomechartHouseholdSensor(coordinator, entry, sensor_type)
        )

    # Per-member sensors
    for member in members:
        for sensor_type in [SENSOR_TASKS_TODAY, SENSOR_TASKS_OVERDUE, SENSOR_TASKS_UPCOMING]:
            entities.append(
                HomechartMemberSensor(coordinator, entry, sensor_type, member)
            )

    async_add_entities(entities)


class HomechartHouseholdSensor(CoordinatorEntity, SensorEntity):
    """Household-level task sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "tasks"

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_household_{sensor_type}"

        # Set name and icon based on type
        if sensor_type == SENSOR_TASKS_TODAY:
            self._attr_name = "Tasks Due Today"
            self._attr_icon = "mdi:calendar-today"
        elif sensor_type == SENSOR_TASKS_OVERDUE:
            self._attr_name = "Overdue Tasks"
            self._attr_icon = "mdi:calendar-alert"
        elif sensor_type == SENSOR_TASKS_UPCOMING:
            self._attr_name = "Upcoming Tasks"
            self._attr_icon = "mdi:calendar-week"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_household")},
        )

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        tasks = self._get_filtered_tasks()
        return len(tasks)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        tasks = self._get_filtered_tasks()

        task_list = []
        for task in tasks[:10]:  # Limit to 10 for attributes
            task_dict = {
                "id": task.id,
                "name": task.name,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "done": task.done,
            }
            if task.details:
                task_dict["details"] = task.details
            if task.project_name:
                task_dict["project"] = task.project_name
            if task.assignees:
                # Resolve assignee IDs to names
                member_map = self.coordinator.data.get("member_map", {})
                task_dict["assignees"] = [
                    member_map.get(a, {}).name if hasattr(member_map.get(a), 'name') else a
                    for a in task.assignees
                ]
            if task.tags:
                task_dict["tags"] = task.tags
            task_list.append(task_dict)

        return {
            ATTR_COUNT: len(tasks),
            ATTR_TASKS: task_list,
        }

    def _get_filtered_tasks(self) -> list:
        """Get tasks filtered by sensor type."""
        if not self.coordinator.data:
            return []

        all_tasks = self.coordinator.data.get("tasks", [])
        today = date.today()

        if self._sensor_type == SENSOR_TASKS_TODAY:
            return [t for t in all_tasks if t.due_date == today and not t.done]

        elif self._sensor_type == SENSOR_TASKS_OVERDUE:
            return [
                t for t in all_tasks if t.due_date and t.due_date < today and not t.done
            ]

        elif self._sensor_type == SENSOR_TASKS_UPCOMING:
            upcoming_days = self._entry.options.get("upcoming_days", 7)
            end_date = today + timedelta(days=upcoming_days)
            return [
                t
                for t in all_tasks
                if t.due_date and today <= t.due_date <= end_date and not t.done
            ]

        return []


class HomechartMemberSensor(CoordinatorEntity, SensorEntity):
    """Per-member task sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "tasks"

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        sensor_type: str,
        member: HomechartHouseholdMember,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._entry = entry
        self._member = member
        self._attr_unique_id = f"{entry.entry_id}_{member.id}_{sensor_type}"

        # Set name and icon based on type
        if sensor_type == SENSOR_TASKS_TODAY:
            self._attr_name = "Tasks Due Today"
            self._attr_icon = "mdi:calendar-today"
        elif sensor_type == SENSOR_TASKS_OVERDUE:
            self._attr_name = "Overdue Tasks"
            self._attr_icon = "mdi:calendar-alert"
        elif sensor_type == SENSOR_TASKS_UPCOMING:
            self._attr_name = "Upcoming Tasks"
            self._attr_icon = "mdi:calendar-week"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._member.id}")},
        )

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        tasks = self._get_filtered_tasks()
        return len(tasks)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        tasks = self._get_filtered_tasks()

        task_list = []
        for task in tasks[:10]:
            task_dict = {
                "id": task.id,
                "name": task.name,
                "due_date": task.due_date.isoformat() if task.due_date else None,
                "done": task.done,
            }
            if task.details:
                task_dict["details"] = task.details
            if task.project_name:
                task_dict["project"] = task.project_name
            if task.tags:
                task_dict["tags"] = task.tags
            task_list.append(task_dict)

        return {
            ATTR_COUNT: len(tasks),
            ATTR_TASKS: task_list,
            "member": self._member.name,
        }

    def _get_filtered_tasks(self) -> list:
        """Get tasks filtered by sensor type AND member."""
        if not self.coordinator.data:
            return []

        all_tasks = self.coordinator.data.get("tasks", [])
        today = date.today()

        # Filter to only this member's tasks
        member_tasks = [
            t for t in all_tasks
            if self._member.id in (t.assignees or [])
        ]

        if self._sensor_type == SENSOR_TASKS_TODAY:
            return [t for t in member_tasks if t.due_date == today and not t.done]

        elif self._sensor_type == SENSOR_TASKS_OVERDUE:
            return [
                t for t in member_tasks if t.due_date and t.due_date < today and not t.done
            ]

        elif self._sensor_type == SENSOR_TASKS_UPCOMING:
            upcoming_days = self._entry.options.get("upcoming_days", 7)
            end_date = today + timedelta(days=upcoming_days)
            return [
                t
                for t in member_tasks
                if t.due_date and today <= t.due_date <= end_date and not t.done
            ]

        return []
