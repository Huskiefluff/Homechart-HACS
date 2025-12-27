# Homechart Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant integration for [Homechart](https://homechart.app) - your household's mission control.

## Features

- **Per-Member Calendars**: Separate calendars for each household member showing their assigned events/tasks
- **Household Calendar**: Shows shared events and tasks (not assigned to specific members)
- **Task Sensors**: Per-member sensors for tasks due today, overdue, and upcoming
- **Todo Lists**: Manage tasks directly from Home Assistant's todo interface
- **Recurring Events**: Full support for daily, weekly, and custom recurrence patterns
- **Services**: Add tasks, complete tasks, and add calendar events via automations
- **Voice Ready**: Perfect for voice assistants - "What's on my calendar today?"

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → Custom repositories
3. Add `Add `https://github.com/Huskiefluff/Homechart-HACS` as an Integration` as an Integration
4. Search for "Homechart" and install
5. Restart Home Assistant

### Manual Installation

1. Download the `custom_components/homechart` folder
2. Copy it to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### Getting Your Session Credentials

Homechart uses session-based authentication. You'll need both the **Session ID** and **Token**.

#### Step 1: Create a New Session

1. Log into [Homechart](https://web.homechart.app) (or your self-hosted instance)
2. Go to **Settings** → **Sessions**
3. Click **+ Add** to create a new session
4. Give it a name like "Home Assistant"
5. You'll see a **Token** displayed - copy this and save it somewhere (you won't see it again!)

#### Step 2: Get the Session ID

1. Still on the **Sessions** page, click the **filter icon** (funnel) at the top
2. Enable **Show ID** filter
3. Now you'll see an **ID** column next to each session
4. Copy the **ID** for your "Home Assistant" session

#### Step 3: Format Your API Key

Combine the Session ID and Token in this format:

```
SESSION_ID:TOKEN
```

**Example:**
```
019b4e1d-d630-79a4-9267-708fd080f79e:019b4e1d-d630-79a9-bf23-49110cff029b
```

### Adding the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Homechart"
3. Enter your combined `ID:TOKEN` string
4. (Optional) If self-hosting, enter your Homechart URL
5. Click Submit

### Reconfiguring

Need to update your API key or URL? Click the **Configure** button on the integration - no need to delete and re-add!

## Entities Created

### Calendars

| Entity | Description |
|--------|-------------|
| `calendar.homechart_household_calendar` | Shared/unassigned events and tasks |
| `calendar.homechart_[member]_calendar` | Events and tasks assigned to that member |

- Events on member calendars show the member's name: `Bathroom (Huskie)`
- Tasks appear prefixed with 📋: `📋 Take out trash (Huskie)`
- Recurring events are fully expanded (daily, weekly, etc.)

### Sensors (Per Member)

| Entity | Description |
|--------|-------------|
| `sensor.[member]_tasks_due_today` | Tasks due today for this member |
| `sensor.[member]_overdue_tasks` | Overdue tasks for this member |
| `sensor.[member]_upcoming_tasks` | Tasks due in the next 7 days |

Each sensor includes attributes with full task details including names, due dates, projects, and assignees.

### Todo Lists

| Entity | Description |
|--------|-------------|
| `todo.homechart_tasks` | All tasks (household-wide view) |
| `todo.homechart_[project]` | One list per Homechart project |

## Services

### `homechart.add_task`

Add a new task to Homechart.

```yaml
service: homechart.add_task
data:
  name: "Take out trash"
  due_date: "2024-01-15"
  details: "Don't forget recycling"
  assignees:
    - "019480ff-5783-75c8-8358-25e402beadcb"  # Member's authAccountID
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
  participants:
    - "019480ff-5783-75c8-8358-25e402beadcb"  # Member's authAccountID
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
            Good morning! You have {{ states('sensor.huskie_tasks_due_today') }} tasks due today
            {% if states('sensor.huskie_overdue_tasks') | int > 0 %}
            and {{ states('sensor.huskie_overdue_tasks') }} overdue tasks
            {% endif %}
```

### Voice Assistant Integration

Perfect for local LLM voice assistants (like Wyoming/Qwen). Expose sensors and calendars for natural queries:

- "What's on my calendar today?"
- "Do I have any overdue tasks?"
- "What tasks are due this week?"

## Understanding Calendar Separation

To avoid duplicate events when viewing multiple calendars:

- **Household Calendar**: Only shows events/tasks with **no participants/assignees** - these are household-wide items
- **Member Calendars**: Only show events/tasks **assigned to that specific member**

This way, if you enable all calendars, each event appears exactly once.

## Troubleshooting

### "Invalid API key" error
- Make sure you're using the `ID:TOKEN` format, not just the token
- The ID and Token are both UUID-format strings
- Try creating a new session and getting fresh credentials

### Tasks not updating
- The integration polls every 1 minute
- You can manually refresh by reloading the integration

### Missing per-member calendars
- Check the logs for errors during setup
- Ensure your Homechart household has members configured

### Self-hosted connection issues
- Ensure your Homechart instance is accessible from Home Assistant
- Check that you're using the correct URL (include `https://` if applicable)
- Default is `https://web.homechart.app`

### Reconfigure not working
- Make sure you have the latest version of the integration
- The reconfigure flow was added in a recent update

## Contributing

Issues and PRs welcome at [github.com/huskie/homechart-ha](Add `https://github.com/Huskiefluff/Homechart-HACS` as an Integration)

## License

MIT
