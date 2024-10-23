import datetime
import traceback

import croniter
import dateutil.tz
import re
from typing import Optional

import boto3

from . import app


scheduler = boto3.client('scheduler')


cron_regex = re.compile(r'cron\(\s*(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*\)')


def get_schedule_time(schedule_name: str) -> Optional[str]:
    try:
        result = scheduler.get_schedule(
            GroupName=app.SCHEDULE_GROUP_NAME,
            Name=schedule_name
        )
    except:
        traceback.print_exc()
        return None

    expression = result.get('ScheduleExpression', '')
    expression_timezone = result.get('ScheduleExpressionTimezone', '')

    match = cron_regex.match(expression)
    if not match:
        return None

    minutes = match.group(1)
    hours = match.group(2)
    day_of_month = match.group(3)
    if day_of_month == '?':
        day_of_month = '*'
    month = match.group(4)
    day_of_week = match.group(5)
    year = match.group(6)

    cron_str = f'{minutes} {hours} {day_of_month} {month} {day_of_week}'

    tz = dateutil.tz.gettz(expression_timezone)
    base = datetime.datetime.now(tz)
    try:
        cron = croniter.croniter(cron_str, base)
    except:
        traceback.print_exc()
        return None

    next_time = cron.get_next(datetime.datetime)
    return next_time.strftime('%A at %I:%M%p')


def is_fourth_weds_this_week() -> bool:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    day_after_tomorrow = today + datetime.timedelta(days=2)
    first_day_of_month = tomorrow.replace(day=1)

    if today.weekday() == 0: # monday
        # tuesday = tomorrow
        wednesday = day_after_tomorrow
    elif today.weekday() == 1: # tuesday
        # tuesday = today
        wednesday = tomorrow

    # the delta between the first day of the month and the fourth weds is at least 21
    return (wednesday - first_day_of_month).days >= 21
