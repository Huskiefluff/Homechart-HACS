"""Todo platform for Homechart integration."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HomechartApi, HomechartTask
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart todo list."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    entities = [
        HomechartTodoList(coordinator, api, entry),
    ]

    # Create additional todo lists per project if there are projects
    if coordinator.data:
        for project in coordinator.data.get("projects", []):
            entities.append(
                HomechartProjectTodoList(coordinator, api, entry, project)
            )

    async_add_entities(entities)


class HomechartTodoList(CoordinatorEntity, TodoListEntity):
    """Representation of a Homechart todo list."""

    _attr_has_entity_name = True
    _attr_name = "Tasks"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self,
        coordinator,
        api: HomechartApi,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the todo list."""
        super().__init__(coordinator)
        self._api = api
        self._attr_unique_id = f"{entry.entry_id}_tasks"
        self._entry = entry

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the todo items."""
        if not self.coordinator.data:
            return []

        items = []
        show_completed = self._entry.options.get("show_completed_tasks", False)

        for task in self.coordinator.data.get("tasks", []):
            # Skip tasks assigned to projects (they'll appear in project-specific lists)
            if task.project_id:
                continue

            # Skip completed unless option is enabled
            if task.done and not show_completed:
                continue

            items.append(self._task_to_todo_item(task))

        return items

    def _task_to_todo_item(self, task: HomechartTask) -> TodoItem:
        """Convert a Homechart task to a TodoItem."""
        return TodoItem(
            uid=task.id,
            summary=task.name,
            status=TodoItemStatus.COMPLETED if task.done else TodoItemStatus.NEEDS_ACTION,
            due=task.due_date,
            description=task.details,
        )

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new todo item."""
        await self.hass.async_add_executor_job(
            self._api.create_task,
            item.summary,
            item.due if isinstance(item.due, date) else None,
            item.description,
            None,  # project_id
            None,  # assignees
            None,  # tags
        )
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a todo item."""
        if item.status == TodoItemStatus.COMPLETED:
            await self.hass.async_add_executor_job(
                self._api.complete_task, item.uid
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.uncomplete_task, item.uid
            )
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        for uid in uids:
            await self.hass.async_add_executor_job(self._api.delete_task, uid)
        await self.coordinator.async_request_refresh()


class HomechartProjectTodoList(CoordinatorEntity, TodoListEntity):
    """Representation of a Homechart project-specific todo list."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(
        self,
        coordinator,
        api: HomechartApi,
        entry: ConfigEntry,
        project: Any,
    ) -> None:
        """Initialize the project todo list."""
        super().__init__(coordinator)
        self._api = api
        self._project = project
        self._attr_unique_id = f"{entry.entry_id}_project_{project.id}"
        self._attr_name = f"Tasks: {project.name}"
        self._entry = entry

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the todo items for this project."""
        if not self.coordinator.data:
            return []

        items = []
        show_completed = self._entry.options.get("show_completed_tasks", False)

        for task in self.coordinator.data.get("tasks", []):
            # Only show tasks for this project
            if task.project_id != self._project.id:
                continue

            # Skip completed unless option is enabled
            if task.done and not show_completed:
                continue

            items.append(
                TodoItem(
                    uid=task.id,
                    summary=task.name,
                    status=TodoItemStatus.COMPLETED if task.done else TodoItemStatus.NEEDS_ACTION,
                    due=task.due_date,
                    description=task.details,
                )
            )

        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new todo item in this project."""
        await self.hass.async_add_executor_job(
            self._api.create_task,
            item.summary,
            item.due if isinstance(item.due, date) else None,
            item.description,
            self._project.id,  # project_id
            None,  # assignees
            None,  # tags
        )
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Update a todo item."""
        if item.status == TodoItemStatus.COMPLETED:
            await self.hass.async_add_executor_job(
                self._api.complete_task, item.uid
            )
        else:
            await self.hass.async_add_executor_job(
                self._api.uncomplete_task, item.uid
            )
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete todo items."""
        for uid in uids:
            await self.hass.async_add_executor_job(self._api.delete_task, uid)
        await self.coordinator.async_request_refresh()
