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
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HomechartApi, HomechartTask, HomechartHouseholdMember
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Homechart todo lists."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["task_coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    members = hass.data[DOMAIN][entry.entry_id]["members"]

    entities = [
        # Household-level task list (all tasks)
        HomechartHouseholdTodoList(coordinator, api, entry),
    ]

    # Per-member task lists
    for member in members:
        entities.append(
            HomechartMemberTodoList(coordinator, api, entry, member)
        )

    # Project-specific lists (under household device)
    if coordinator.data:
        for project in coordinator.data.get("projects", []):
            entities.append(
                HomechartProjectTodoList(coordinator, api, entry, project)
            )

    async_add_entities(entities)


class HomechartHouseholdTodoList(CoordinatorEntity, TodoListEntity):
    """Household-level todo list showing all tasks."""

    _attr_has_entity_name = True
    _attr_name = "All Tasks"
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
        self._attr_unique_id = f"{entry.entry_id}_household_tasks"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_household")},
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the todo items."""
        if not self.coordinator.data:
            return []

        items = []
        show_completed = self._entry.options.get("show_completed_tasks", False)
        member_map = self.coordinator.data.get("member_map", {})

        for task in self.coordinator.data.get("tasks", []):
            if task.done and not show_completed:
                continue

            # Build description with assignee info
            description = task.details or ""
            if task.assignees:
                assignee_names = [
                    member_map.get(a).name if member_map.get(a) else a
                    for a in task.assignees
                ]
                if assignee_names:
                    assignee_str = f"Assigned to: {', '.join(assignee_names)}"
                    description = f"{assignee_str}\n{description}" if description else assignee_str

            items.append(
                TodoItem(
                    uid=task.id,
                    summary=task.name,
                    status=TodoItemStatus.COMPLETED if task.done else TodoItemStatus.NEEDS_ACTION,
                    due=task.due_date,
                    description=description,
                )
            )

        return items

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Create a new todo item."""
        await self.hass.async_add_executor_job(
            self._api.create_task,
            item.summary,
            item.due if isinstance(item.due, date) else None,
            item.description,
            None,
            None,
            None,
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


class HomechartMemberTodoList(CoordinatorEntity, TodoListEntity):
    """Per-member todo list."""

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
        member: HomechartHouseholdMember,
    ) -> None:
        """Initialize the todo list."""
        super().__init__(coordinator)
        self._api = api
        self._member = member
        self._attr_unique_id = f"{entry.entry_id}_{member.id}_tasks"
        self._attr_name = "Tasks"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._member.id}")},
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the todo items for this member."""
        if not self.coordinator.data:
            return []

        items = []
        show_completed = self._entry.options.get("show_completed_tasks", False)

        for task in self.coordinator.data.get("tasks", []):
            # Only show tasks assigned to this member
            if self._member.id not in (task.assignees or []):
                continue

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
        """Create a new todo item assigned to this member."""
        await self.hass.async_add_executor_job(
            self._api.create_task,
            item.summary,
            item.due if isinstance(item.due, date) else None,
            item.description,
            None,
            [self._member.id],  # Assign to this member
            None,
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
    """Project-specific todo list."""

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
        self._attr_name = f"Project: {project.name}"
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info (under household)."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_household")},
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the todo items for this project."""
        if not self.coordinator.data:
            return []

        items = []
        show_completed = self._entry.options.get("show_completed_tasks", False)
        member_map = self.coordinator.data.get("member_map", {})

        for task in self.coordinator.data.get("tasks", []):
            if task.project_id != self._project.id:
                continue

            if task.done and not show_completed:
                continue

            # Build description with assignee info
            description = task.details or ""
            if task.assignees:
                assignee_names = [
                    member_map.get(a).name if member_map.get(a) else a
                    for a in task.assignees
                ]
                if assignee_names:
                    assignee_str = f"Assigned to: {', '.join(assignee_names)}"
                    description = f"{assignee_str}\n{description}" if description else assignee_str

            items.append(
                TodoItem(
                    uid=task.id,
                    summary=task.name,
                    status=TodoItemStatus.COMPLETED if task.done else TodoItemStatus.NEEDS_ACTION,
                    due=task.due_date,
                    description=description,
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
            self._project.id,
            None,
            None,
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
