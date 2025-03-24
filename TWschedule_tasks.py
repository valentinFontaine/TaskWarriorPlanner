import json
import subprocess
import datetime
import re
from collections import defaultdict
from operator import itemgetter


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

def sort_tasks_by_urgency(tasks):
    """ 
    Sort the tasks by the urgency column in descneding order

    """
    return sorted(tasks, key=itemgetter('urgency'), reverse=True)

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

def get_current_slot(current_date, timeslots):
    #Get the current day of the week
    day_of_week = current_date.strftime('%A') 

    for slot_name, slot_times, in timeslots.items():
        time_ranges = slot_times.get(day_of_week, [])

        for time_range in time_ranges:
            start_time_str, end_time_str = time_range.split('-')
            start_time = datetime.datetime.strptime(start_time_str, '%H:%M')
            end_time = datetime.datetime.strptime(end_time_str, '%H:%M')

            start_time = current_date.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
            end_time = current_date.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
            
            if start_time <= current_date <= end_time:
                return slot_name, end_time
            
    return "", current_date

def get_next_blocked_time(current_date, end_time, scheduled_tasks): 
    #get the next start time of a scheduled task
    next_time = end_time
    for task in scheduled_tasks:
        scheduled_time = task['scheduled'] # datetime.datetime.strptime(task['scheduled'], '%Y%m%dT%H%M%SZ')
        if scheduled_time < next_time and scheduled_time > current_date:
            next_time = scheduled_time
    return next_time


def schedule_tasks_VF(tasks, config):
    time_slots = config['timeSlots']
    commute_time = config['commuteTime']
    planned_duration_days = config['plannedDurationDays']
    deep_work_limit = config['deepWorkLimit']
    free_time_hours = config['freeTimeHours']

    start_date = datetime.datetime.now() # + datetime.timedelta(hours=4)
    start_date = start_date.replace(second=0, microsecond=0)
    end_date = start_date + datetime.timedelta(days=planned_duration_days)
    scheduled_tasks = []

    #Ajout des taches deja plannifiees 
    for task in tasks:
        if 'scheduled' in task:
            scheduled_time = datetime.datetime.strptime(task['scheduled'], '%Y%m%dT%H%M%SZ')
            if scheduled_time > start_date and scheduled_time < end_date:
                scheduled_tasks.append(task)

    #Planifie les differentes taches
    current_dateTime = start_date
    current_slot = ""

    while current_dateTime < end_date:
        current_slot, end_slot = get_current_slot(current_dateTime, time_slots)
        next_blocked_time = get_next_blocked_time(current_dateTime, end_date,  scheduled_tasks)
        
        #print(f"Current_Time : {current_dateTime.isoformat()} | current_slot: {current_slot} | end_slot: {end_slot.isoformat()} | next_blocket_time: {next_blocked_time.isoformat()}")
        est_time = 10
        for task in tasks: 
            #on ignore les les taches deja planifiees ou sans estTime
            if task in scheduled_tasks: 
                continue
            if 'estTime' not in task:
                continue
            if current_slot not in task['tags']:
                continue
            
            est_time = parse_duration(task['estTime'])
            end_time = current_dateTime + datetime.timedelta(minutes=est_time)
            #print(f"Description : {task['description']} | est_time: {est_time}| end_time: {end_time} | {end_time > end_slot} | {end_time > next_blocked_time} ")

            if end_time > end_slot or end_time > next_blocked_time:
                continue

            task['scheduled'] = current_dateTime
            print(f"Task: {task['description']} scheduled at {task['scheduled'].isoformat()} ")
            scheduled_tasks.append(task)
            break

        current_dateTime = current_dateTime + datetime.timedelta(minutes=est_time) + datetime.timedelta(minutes=5)
    
    print("sortie")
    return scheduled_tasks


# Display summary of scheduled tasks
def display_summary(scheduled_tasks):
    for task in scheduled_tasks:
        scheduled_time = task['scheduled'] # datetime.datetime.strptime(task['scheduled'], '%Y%m%dT%H%M%SZ')
        est_time = parse_duration(task['estTime'])
        end_time = scheduled_time + datetime.timedelta(minutes=est_time)
        print(f"Task: {task['description']}")
        print(f"Day: {scheduled_time.strftime('%A')}")
        print(f"Start Time: {scheduled_time.strftime('%H:%M')}")
        print(f"End Time: {end_time.strftime('%H:%M')}")
        print('---')

#Print Function 
def print_task_table(tasks):
    """Print the list of task an only shows the columns user_ID, urgency, description"""
    for task in tasks: 
        print(f"| {task['id']} |  {task['urgency']} | {task['description']} |")
    return True

# Main function
def main():
    config = load_config('config.json')
    tasks = sort_tasks_by_urgency(get_task_data())
    
    #print_task_table(sorted(tasks, key=itemgetter('urgency'), reverse=True))    
    #print_task_table(tasks)    

    scheduled_tasks = schedule_tasks_VF(tasks, config)

    print("Ceci est le calendrier propose")
    display_summary(scheduled_tasks)
    
    """
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
    """
    confirm = input("Do you want to proceed with the scheduling? (yes/no): ")
    if confirm.lower() == 'yes':
        #modify_tasks(scheduled_tasks)
        print("Scheduling code to be written")
    else:
        print("Scheduling aborted.")

if __name__ == '__main__':
    main()
