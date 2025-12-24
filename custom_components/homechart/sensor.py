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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_COUNT,
    ATTR_TASKS,
    DOMAIN,
    SENSOR_TASKS_OVERDUE,
    SENSOR_TASKS_TODAY,
    SENSOR_TASKS_UPCOMING,
)

SENSOR_DESCRIPTIONS = [
    SensorEntityDescription(
        key=SENSOR_TASKS_TODAY,
        name="Tasks Due Today",
        icon="mdi:calendar-today",
        native_unit_of_measurement="tasks",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_TASKS_OVERDUE,
        name="Overdue Tasks",
        icon="mdi:calendar-alert",
        native_unit_of_measurement="tasks",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key=SENSOR_TASKS_UPCOMING,
        name="Upcoming Tasks",
        icon="mdi:calendar-week",
        native_unit_of_measurement="tasks",
        state_class=SensorStateClass.MEASUREMENT,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]

    entities = [
        HomechartTaskSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class HomechartTaskSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Homechart task sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._entry = entry

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
                task_dict["assignees"] = task.assignees
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
        key = self.entity_description.key

        if key == SENSOR_TASKS_TODAY:
            return [t for t in all_tasks if t.due_date == today and not t.done]

        elif key == SENSOR_TASKS_OVERDUE:
            return [
                t for t in all_tasks if t.due_date and t.due_date < today and not t.done
            ]

        elif key == SENSOR_TASKS_UPCOMING:
            upcoming_days = self._entry.options.get("upcoming_days", 7)
            end_date = today + timedelta(days=upcoming_days)
            return [
                t
                for t in all_tasks
                if t.due_date and today <= t.due_date <= end_date and not t.done
            ]

        return []
