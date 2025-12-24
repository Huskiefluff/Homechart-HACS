"""Constants for the Homechart integration."""
from datetime import timedelta
from typing import Final

DOMAIN: Final = "homechart"
DEFAULT_NAME: Final = "Homechart"

# API
DEFAULT_URL: Final = "https://web.homechart.app"
API_BASE_PATH: Final = "/api/v1"

# Config keys
CONF_API_KEY: Final = "api_key"
CONF_URL: Final = "url"

# Update intervals
SCAN_INTERVAL: Final = timedelta(minutes=5)
CALENDAR_SCAN_INTERVAL: Final = timedelta(minutes=15)

# Platforms
PLATFORMS: Final = ["sensor", "calendar", "todo"]

# Sensor types
SENSOR_TASKS_TODAY: Final = "tasks_today"
SENSOR_TASKS_OVERDUE: Final = "tasks_overdue"
SENSOR_TASKS_UPCOMING: Final = "tasks_upcoming"

# Attributes
ATTR_TASKS: Final = "tasks"
ATTR_COUNT: Final = "count"
ATTR_TASK_NAME: Final = "name"
ATTR_TASK_DUE: Final = "due_date"
ATTR_TASK_DONE: Final = "done"
ATTR_TASK_DETAILS: Final = "details"
ATTR_TASK_ASSIGNEES: Final = "assignees"
ATTR_TASK_TAGS: Final = "tags"
ATTR_TASK_PROJECT: Final = "project"

# Services
SERVICE_ADD_TASK: Final = "add_task"
SERVICE_COMPLETE_TASK: Final = "complete_task"
SERVICE_ADD_EVENT: Final = "add_event"
