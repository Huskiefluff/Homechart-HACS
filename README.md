# Homechart Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant integration for [Homechart](https://homechart.app) - your household's mission control.

## Features

- **Task Sensors**: Track tasks due today, overdue tasks, and upcoming tasks
- **Calendar Entity**: View Homechart events and tasks with due dates on your HA calendar
- **Todo Lists**: Manage tasks directly from Home Assistant's todo interface
  - Main tasks list
  - Separate todo lists per Homechart project
- **Services**: Add tasks, complete tasks, and add calendar events via automations

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → Custom repositories
3. Add `https://github.com/huskie/homechart-ha` as an Integration
4. Search for "Homechart" and install
5. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/homechart` folder
2. Copy it to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### Getting Your API Key

1. Log into Homechart (web or app)
2. Go to **Settings** → **Account** → **Sessions**
3. Click **Create API Key** (or similar)
4. Give it a name like "Home Assistant"
5. Copy the generated key

### Adding the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Homechart"
3. Enter your API key
4. (Optional) If self-hosting, enter your Homechart URL
5. Click Submit

## Entities Created

### Sensors

| Entity | Description |
|--------|-------------|
| `sensor.tasks_due_today` | Number of tasks due today |
| `sensor.overdue_tasks` | Number of overdue tasks |
| `sensor.upcoming_tasks` | Number of tasks due in the next 7 days |

Each sensor includes attributes with the full task list (up to 10 items) including names, due dates, projects, and assignees.

### Calendar

| Entity | Description |
|--------|-------------|
| `calendar.homechart_calendar` | Combined calendar showing events and tasks |

Tasks appear as all-day events prefixed with 📋.

### Todo Lists

| Entity | Description |
|--------|-------------|
| `todo.homechart_tasks` | Main task list (tasks not in projects) |
| `todo.homechart_tasks_[project]` | One list per Homechart project |

## Services

### `homechart.add_task`

Add a new task to Homechart.

```yaml
service: homechart.add_task
data:
  name: "Take out trash"
  due_date: "2024-01-15"
  details: "Don't forget recycling"
```

### `homechart.complete_task`

Mark a task as complete.

```yaml
service: homechart.complete_task
data:
  task_id: "abc123-def456"
```

### `homechart.add_event`

Add a calendar event.

```yaml
service: homechart.add_event
data:
  name: "Doctor Appointment"
  date_start: "2024-01-15"
  time_start: "14:30"
  duration: 60
  location: "123 Main St"
```

## Options

In the integration options, you can configure:

- **Show completed tasks**: Include completed tasks in todo lists
- **Upcoming days**: How many days ahead to look for the upcoming tasks sensor (default: 7)

## Example Automations

### Morning Task Announcement

```yaml
automation:
  - alias: "Morning Task Announcement"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: tts.speak
        target:
          entity_id: media_player.kitchen_speaker
        data:
          message: >
            Good morning! You have {{ states('sensor.tasks_due_today') }} tasks due today
            {% if states('sensor.overdue_tasks') | int > 0 %}
            and {{ states('sensor.overdue_tasks') }} overdue tasks
            {% endif %}
```

### Voice Assistant Task Query

For use with your local LLM voice assistant, expose these sensors and create intents or tool calls to query task data.

## Troubleshooting

### "Invalid API key" error
- Make sure you created an API key, not just copied your password
- API keys are long strings that look like random characters
- Try creating a new API key

### Tasks not updating
- The integration polls every 5 minutes by default
- You can manually refresh by reloading the integration

### Self-hosted connection issues
- Ensure your Homechart instance is accessible from Home Assistant
- Check that you're using the correct URL (include `https://` if applicable)

## Contributing

Issues and PRs welcome at [github.com/huskie/homechart-ha](https://github.com/huskie/homechart-ha)

## License

MIT
