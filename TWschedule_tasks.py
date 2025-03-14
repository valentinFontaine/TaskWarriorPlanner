import json
import subprocess
import datetime
import dateutil.parser
import dateutil.relativedelta
import pytz
import re


def parse_duration(duration_str):
    """
    Parses an ISO-8601 duration string into total minutes.

    Args:
        duration_str (str): The ISO-8601 duration string to parse.

    Returns:
        int: The total duration in minutes.
    """
    if not duration_str:
        return 0

    match = re.match(r'P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?', duration_str)
    if not match:
        return None  # Invalid format

    years, months, days, hours, minutes, seconds = match.groups()

    total_minutes = 0
    if years:
        total_minutes += int(years) * 525600  # Approximate minutes in a year
    if months:
        total_minutes += int(months) * 43800  # Approximate minutes in a month
    if days:
        total_minutes += int(days) * 1440
    if hours:
        total_minutes += int(hours) * 60
    if minutes:
        total_minutes += int(minutes)
    if seconds:
        total_minutes += int(seconds) / 60.0

    return int(total_minutes)

def format_duration(minutes):
    """
    Formats minutes into a duration string like '1h30m'.

    Args:
        minutes (int): The duration in minutes.

    Returns:
        str: The formatted duration string.
    """
    hours = minutes // 60
    minutes %= 60
    return f"{hours}h{minutes}m" if hours else f"{minutes}m"

def get_task_data():
    """
    Retrieves tasks from TaskWarrior using 'task export'.

    Returns:
        list: A list of task dictionaries.
    """
    try:
        result = subprocess.run(['task', '+PENDING', 'export'], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running TaskWarrior: {e}")
        return []


def load_config(config_file):
    """Loads and validates the configuration from a JSON file."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        # Add validation here if needed
        return config
    except FileNotFoundError:
        print(f"Error: {config_file} not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in {config_file}.")
        return None

def check_tasks_without_est(tasks):
    """Checks for tasks without estimated time and prompts the user."""
    tasks_without_est = [task for task in tasks if 'estTime' not in task]
    if tasks_without_est:
        print("Tasks without estTime found:")
        for task in tasks_without_est:
            print(f"- {task['description']}")
        if input("Abort? (y/n): ").lower() == 'y':
            return False
    return True

# Main function
def main():
    config = load_config('config.json')
    task_output = run_task_command(['task', 'next'])
    tasks = parse_tasks(task_output)

    # Check for tasks without estTime
    if not check_tasks_without_est(tasks):
        return

    # Check for invalid estTime format
    for task in tasks:
        if 'estTime' in task:
            try:
                parse_duration(task['estTime'])
            except ValueError:
                print(f"Invalid 'estTime' format found in task {task['id']}. Please abort.")
                return

    scheduled_tasks = schedule_tasks(tasks, config)
    display_summary(scheduled_tasks)

    confirm = input("Do you want to proceed with the scheduling? (yes/no): ")
    if confirm.lower() == 'yes':
        modify_tasks(scheduled_tasks)
    else:
        print("Scheduling aborted.")

if __name__ == '__main__':
    main()
