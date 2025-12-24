"""The Homechart integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HomechartApi, HomechartApiError, HomechartHouseholdMember
from .const import (
    CONF_API_KEY,
    CONF_URL,
    DEFAULT_URL,
    DOMAIN,
    SCAN_INTERVAL,
    SERVICE_ADD_TASK,
    SERVICE_COMPLETE_TASK,
    SERVICE_ADD_EVENT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR, Platform.TODO]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Homechart from a config entry."""
    api = HomechartApi(
        url=entry.data.get(CONF_URL, DEFAULT_URL),
        api_key=entry.data[CONF_API_KEY],
    )

    # Test connection
    if not await hass.async_add_executor_job(api.test_connection):
        _LOGGER.error("Failed to connect to Homechart API")
        return False

    # Fetch household members for device creation
    members = await hass.async_add_executor_job(api.get_household_members)
    _LOGGER.debug("Found %d household members: %s", len(members), [m.name for m in members])

    # Create coordinators
    task_coordinator = HomechartTaskCoordinator(hass, api, members)
    event_coordinator = HomechartEventCoordinator(hass, api, members)

    # Fetch initial data
    await task_coordinator.async_config_entry_first_refresh()
    await event_coordinator.async_config_entry_first_refresh()

    # Register devices
    device_registry = dr.async_get(hass)
    
    # Household device (main device)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}_household")},
        name="Homechart Household",
        manufacturer="Homechart",
        model="Household",
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    
    # Per-member devices
    for member in members:
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_{member.id}")},
            name=f"Homechart: {member.name}",
            manufacturer="Homechart",
            model="Member",
            entry_type=dr.DeviceEntryType.SERVICE,
            via_device=(DOMAIN, f"{entry.entry_id}_household"),
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "task_coordinator": task_coordinator,
        "event_coordinator": event_coordinator,
        "members": members,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Homechart services."""

    async def handle_add_task(call: ServiceCall) -> None:
        """Handle add task service call."""
        for entry_data in hass.data[DOMAIN].values():
            api: HomechartApi = entry_data["api"]
            coordinator = entry_data["task_coordinator"]

            await hass.async_add_executor_job(
                api.create_task,
                call.data["name"],
                call.data.get("due_date"),
                call.data.get("details"),
                call.data.get("project_id"),
                call.data.get("assignees"),
                call.data.get("tags"),
            )

            await coordinator.async_request_refresh()
            break

    async def handle_complete_task(call: ServiceCall) -> None:
        """Handle complete task service call."""
        for entry_data in hass.data[DOMAIN].values():
            api: HomechartApi = entry_data["api"]
            coordinator = entry_data["task_coordinator"]

            await hass.async_add_executor_job(api.complete_task, call.data["task_id"])

            await coordinator.async_request_refresh()
            break

    async def handle_add_event(call: ServiceCall) -> None:
        """Handle add event service call."""
        for entry_data in hass.data[DOMAIN].values():
            api: HomechartApi = entry_data["api"]
            coordinator = entry_data["event_coordinator"]

            await hass.async_add_executor_job(
                api.create_event,
                call.data["name"],
                call.data["date_start"],
                call.data.get("date_end"),
                call.data.get("time_start"),
                call.data.get("duration"),
                call.data.get("details"),
                call.data.get("location"),
                call.data.get("participants"),
            )

            await coordinator.async_request_refresh()
            break

    # Only register if not already registered
    if not hass.services.has_service(DOMAIN, SERVICE_ADD_TASK):
        hass.services.async_register(DOMAIN, SERVICE_ADD_TASK, handle_add_task)

    if not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK):
        hass.services.async_register(DOMAIN, SERVICE_COMPLETE_TASK, handle_complete_task)

    if not hass.services.has_service(DOMAIN, SERVICE_ADD_EVENT):
        hass.services.async_register(DOMAIN, SERVICE_ADD_EVENT, handle_add_event)


class HomechartTaskCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch task data."""

    def __init__(
        self, hass: HomeAssistant, api: HomechartApi, members: list[HomechartHouseholdMember]
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Homechart Tasks",
            update_interval=SCAN_INTERVAL,
        )
        self.api = api
        self.members = members
        # Build ID to name mapping
        self.member_map = {m.id: m for m in members}

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            tasks = await self.hass.async_add_executor_job(self.api.get_tasks)
            projects = await self.hass.async_add_executor_job(self.api.get_projects)

            return {
                "tasks": tasks,
                "projects": projects,
                "members": self.members,
                "member_map": self.member_map,
            }
        except HomechartApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err


class HomechartEventCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch event data."""

    def __init__(
        self, hass: HomeAssistant, api: HomechartApi, members: list[HomechartHouseholdMember]
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Homechart Events",
            update_interval=timedelta(minutes=15),
        )
        self.api = api
        self.members = members
        self.member_map = {m.id: m for m in members}

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            events = await self.hass.async_add_executor_job(self.api.get_events)
            return {
                "events": events,
                "members": self.members,
                "member_map": self.member_map,
            }
        except HomechartApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
