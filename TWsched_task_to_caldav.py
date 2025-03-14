import caldav
import uuid
import configparser
import subprocess
import json
from datetime import datetime, timedelta, timezone
import re

config = configparser.ConfigParser()
config.read("config.ini")
CALDAV_URL = config["CalDAV"]["url"] 
USERNAME = config["CalDAV"]["username"]
PASSWORD = config["CalDAV"]["password"]
CALENDAR_NAME = "Perso"  # Or whatever your calendar is called

calendar_mapping = {
    "pro": "Pro", 
    "sport": "Sport",
    "asso": "Asso",
    "repas": "repas",
    "perso": "Perso",
    # Add more tag-to-calendar mappings as needed
}

def determine_calendar(task_tags, calendar_mapping):
    """Determines the calendar based on task tags."""
    for tag in task_tags:
        if tag in calendar_mapping:
            return calendar_mapping[tag]  # Return the calendar name

    return "Perso"  # Return a default calendar if no matching tag is found

def export_taskwarrior_scheduled_tasks():
    """Exports scheduled tasks from Taskwarrior in a CalDAV-friendly format."""
    try:
        # Run Taskwarrior command to get scheduled tasks in JSON format
        result = subprocess.run(
            ["task", "+SCHEDULED", "+PENDING",  "export"],
            capture_output=True,
            text=True,
            check=True,
        )
        tasks = json.loads(result.stdout)
    
        caldav_events = []
        for task in tasks:
            #print(json.dumps(task, indent=4)) #prints in json format for easy reading.
            if "scheduled" in task:
                scheduled_date_str = task["scheduled"]
                description = task.get("description", "")
                uuid = task.get("uuid", "")
                tags = task.get("tags", [])
                est_time_str = task["estTime"]
                calendar = determine_calendar(tags, calendar_mapping) 
                
                try:
                    # Parse the scheduled date string
                    scheduled_datetime = datetime.fromisoformat(scheduled_date_str.replace("Z", "+00:00"))  # Handle UTC

                    if "estTime" in task:
                        duration = parse_iso8601_duration(est_time_str)
                        end_datetime = scheduled_datetime + duration
                    else:
                        end_datetime = scheduled_datetime + timedelta(hours=1)

                except ValueError as e:
                    print(f"Error parsing scheduled date for task '{description}': {e}")
                    end_datetime = scheduled_datetime + timedelta(hours=1) #default to 1 hour if error.
                    continue
                except Exception as e:
                    print(f"An unexpected error occurred while parsing estTime: {e}")
                    end_datetime = scheduled_datetime + timedelta(hours=1)

                caldav_event = {
                    "summary": description,
                    "start_time": scheduled_datetime.isoformat(),
                    "end_time": end_datetime.isoformat(),
                    "uuid": uuid,
                    "tags": tags,
                    "taskwarrior_scheduled_date": scheduled_date_str,
                    "calendar": calendar
                }
                caldav_events.append(caldav_event)
        return caldav_events

    except subprocess.CalledProcessError as e:
        print(f"Error running Taskwarrior: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing Taskwarrior JSON output: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def parse_iso8601_duration(duration_string):
    """Parses an ISO 8601 duration string and returns a timedelta object."""

    # Regular expression to match ISO 8601 duration format
    duration_regex = re.compile(r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

    match = duration_regex.match(duration_string)

    if not match:
        raise ValueError("Invalid ISO 8601 duration string")

    years, months, days, hours, minutes, seconds = match.groups()

    if not any(match.groups()):  # check if all groups are None, meaning an empty duration
        raise ValueError("Invalid ISO 8601 duration string. At least one duration component must be specified.")

    total_seconds = 0

    if years:
        total_seconds += int(years) * 365 * 24 * 3600  # Approximation: 1 year = 365 days
    if months:
        total_seconds += int(months) * 30 * 24 * 3600  # Approximation: 1 month = 30 days
    if days:
        total_seconds += int(days) * 24 * 3600
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)

    return timedelta(seconds=total_seconds)


def export_tasks():
    import subprocess
    subprocess.run(['task', 'scheduled', 'export'], stdout=open('tasks.json', 'w'))

def convert_to_ics():
    with open('tasks.json') as f:
        tasks = json.load(f)

    for task in tasks:
        if 'scheduled' in task:
            event = Event()
            event.name = task['description']
            event.begin = datetime.strptime(task['scheduled'], '%Y%m%dT%H%M%SZ')
            event.uid = task['uuid']  # Use task UUID as event UID
            cal.events.add(event)

def create_caldav_events(caldav_url, username, password, scheduled_tasks):
    """Creates CalDAV events from a list of scheduled tasks."""

    try:
        client = caldav.DAVClient(url=caldav_url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()

        for task in scheduled_tasks:
            calendar_name = task['calendar']
            event_summary = task['summary']
            start_time_str = task['start_time']
            end_time_str = task['end_time']
            event_uuid = task['uuid']

            try:
                start_time = datetime.fromisoformat(start_time_str)
                end_time = datetime.fromisoformat(end_time_str)

                target_calendar = None
                for calendar in calendars:
                    if calendar.name == calendar_name:
                        target_calendar = calendar
                        break

                if target_calendar is None:
                    print(f"Calendar '{calendar_name}' not found.")
                    continue  # Skip to the next task

                event_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//YourApp//EN
BEGIN:VEVENT
UID:{event_uuid}
DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}
DTSTART;TZID=UTC:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND;TZID=UTC:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{event_summary}
END:VEVENT
END:VCALENDAR
"""

                target_calendar.save_event(event_data)
                print(f"Event '{event_summary}' created successfully.")

            except ValueError as e:
                print(f"Error parsing date/time strings: {e}")
            except Exception as e:
                print(f"Error creating CalDAV event: {e}")

    except caldav.exceptions.DAVError as e:
        print(f"CalDAV error: {e}")
    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
    except Exception as e:
        print(f"Unexpected CalDAV error: {e}")

if __name__ == "__main__":
    scheduled_tasks = export_taskwarrior_scheduled_tasks()
    if scheduled_tasks:
        create_caldav_events(CALDAV_URL, USERNAME, PASSWORD, scheduled_tasks)
