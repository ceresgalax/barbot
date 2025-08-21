"""
Lambda functions intended to be called from Step Functions go here
"""
import os
import random
import traceback
from typing import Dict, Any, List, Callable, Awaitable, Optional

import telegram
from mypy_boto3_scheduler import EventBridgeSchedulerClient

from . import bars, database, util, schedule_util
from .app import AppSettings, asyncio_loop, BARNIGHT_HASHTAG
from .database import Database


class SequenceServices(object):
    def __init__(self, db: Database, bot: telegram.Bot, scheduler: EventBridgeSchedulerClient, app: AppSettings):
        self.db = db
        self.bot = bot
        self.scheduler = scheduler
        self.app = app


# This is the entry point called from the sequence lambda function.
def handle_function_call(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    event_type = event['barnight_event_type']
    func = event_funcs[event_type]

    app_settings = AppSettings(os.environ)
    db = database.DynamoDatabase(app_settings)
    assert app_settings.TELEGRAM_BOT_TOKEN is not None
    bot = telegram.Bot(
        token=app_settings.TELEGRAM_BOT_TOKEN
    )
    scheduler = schedule_util.make_scheduler()
    services = SequenceServices(db, bot, scheduler, app_settings)
    return asyncio_loop.run_until_complete(func(event, services))


async def handle_ask_for_suggestions(event: Dict[str, Any], services: SequenceServices) -> Dict[str, Any]:
    app_settings = services.app

    scheduled_event = schedule_util.get_active_scheduled_event(services.db, app_settings)
    if scheduled_event:
        # This cycle is a scheduled event!
        def get_message(bar_name_markdown: str) -> str:
            return f'Next bar night will be at {bar_name_markdown}\\!'
        await send_winning_result(scheduled_event.venue_name, services, get_message, reply_to_message_id=None)
        return {}

    text = f'It\'s time for bar night suggestions! Message @{app_settings.BOT_USERNAME} or end a message with ' \
           f'{BARNIGHT_HASHTAG} to input a suggestion!'
    poll_time = schedule_util.get_schedule_time(services.scheduler, app_settings, app_settings.CREATE_POLL_SCHEDULE_NAME)
    if poll_time:
        text += f' Poll will be created on {poll_time}.'

    await services.bot.send_message(chat_id=app_settings.MAIN_CHAT_ID, text=text)
    return {}


async def handle_create_poll(event: Dict[str, Any], services: SequenceServices) -> Dict[str, Any]:
    db = services.db
    bot = services.bot
    app_settings = services.app

    if schedule_util.get_active_scheduled_event(db, app_settings):
        # Skip due to scheduled event
        return {}

    db.set_current_poll_id(0)
    suggestions = db.get_current_suggestions(bypass_cache=True)

    if len(suggestions) == 0:
        send_message_result = await bot.send_message(
            chat_id=app_settings.MAIN_CHAT_ID,
            text='Oops! No one suggested anything for barnight. I\'m gonna sit this one out...',
        )
    elif len(suggestions) == 1:
        def get_main_chat_message(bar_name_markdown: str) -> str:
            return f'There was only one suggestion, and it was for {bar_name_markdown}\\.'
        await send_winning_result(suggestions[0].venue, services, get_main_chat_message, reply_to_message_id=None)
    else:
        try:
            png, png_text = await util.get_map_suggestions_message_data(bars.Bars(app_settings.BAR_SPREADSHEET), suggestions, app_settings)
            if png:
                await bot.send_photo(
                    app_settings.MAIN_CHAT_ID,
                    png,
                    png_text,
                    parse_mode='MarkdownV2',
                )
            else:
                print('Could not map any bars for the poll!')
        except Exception as err:
            print(f'Could not send the map before the poll: {err}')
        try:
            send_poll_result = await bot.send_poll(
                chat_id=app_settings.MAIN_CHAT_ID,
                question='Where are we going for barnight? (multiple choice)',
                options=[x.venue for x in suggestions],
                is_anonymous=False,
                type='regular',
                allows_multiple_answers=True
            )
        except:
            traceback.print_exc()
            error_message_result = await bot.send_message(
                app_settings.MAIN_CHAT_ID,
                'Oh no! I was unable to create a poll for barnight! Please continue the process manually. '
                'Here is the list of suggested venues:\n\n'
                + util.get_list_suggestions_message_text(db.get_current_suggestions(bypass_cache=True))
            )
            db.clear_suggestions()
            await bot.pin_chat_message(chat_id=app_settings.MAIN_CHAT_ID, message_id=error_message_result.message_id)
            return {}

        poll_id = send_poll_result.id
        db.set_current_poll_id(poll_id)
        await bot.pin_chat_message(chat_id=app_settings.MAIN_CHAT_ID, message_id=poll_id)

    db.clear_suggestions()
    return {}


async def handle_poll_reminder(event: Dict[str, Any], services: SequenceServices) -> Dict[str, Any]:
    app_settings = services.app

    if schedule_util.get_active_scheduled_event(services.db, app_settings):
        # Skipped when scheduled event is active
        return {}

    poll_id = services.db.get_current_poll_id()
    if not poll_id:
        return {}

    text = "REMINDER: Don't forget to vote!"
    close_time = schedule_util.get_schedule_time(services.scheduler, app_settings, app_settings.CLOSE_POLL_SCHEDULE_NAME)
    if close_time:
        text += f' The poll will close on {close_time}.'

    await services.bot.send_message(
        chat_id=app_settings.MAIN_CHAT_ID,
        text=text,
        reply_to_message_id=poll_id
    )
    return {}


async def handle_choose_winner(event: Dict[str, Any], services: SequenceServices) -> Dict[str, Any]:
    db = services.db
    bot = services.bot
    app_settings = services.app

    if schedule_util.get_active_scheduled_event(db, app_settings):
        return {}

    poll_id = db.get_current_poll_id()

    if not poll_id:
        return {}

    try:
        poll = await bot.stop_poll(
            chat_id=app_settings.MAIN_CHAT_ID,
            message_id=poll_id
        )
    except:
        traceback.print_exc()
        error_message_result = await bot.send_message(
            app_settings.MAIN_CHAT_ID,
            'Oh no! I was unable to close the poll for barnight! '
            'Please close the poll (if it wasn\'t closed already) and declare a winner for me.'
        )
        db.set_current_poll_id(0)
        await bot.pin_chat_message(chat_id=app_settings.MAIN_CHAT_ID, message_id=error_message_result.message_id)
        return {}

    top_options: List[telegram.PollOption] = []
    max_votes = 0

    for option in poll.options:
        if option.voter_count == max_votes:
            top_options.append(option)
        elif option.voter_count > max_votes:
            max_votes = option.voter_count
            top_options.clear()
            top_options.append(option)

    chosen_option = random.choice(top_options)

    bar_name = chosen_option.text

    def get_main_chat_message(bar_name_markdown: str) -> str:
        message = f'Calling it for {bar_name_markdown}\\!'
        if len(top_options) > 1:
            message += util.escape_markdown_v2(f' (Chosen randomly out of the top {len(top_options)} options)')
        return message

    await send_winning_result(bar_name, services, get_main_chat_message, poll_id)

    db.set_current_poll_id(0)
    return {}


async def send_winning_result(
    bar_name: str,
    services: SequenceServices,
    main_chat_message_func: Callable[[str], str],
    reply_to_message_id: Optional[int],
) -> None:
    app_settings = services.app
    bot = services.bot

    # Remove redundant punctuation
    bar_name_no_punctuation = bar_name
    if bar_name.endswith(('.', '?', '!')):
        bar_name_no_punctuation = bar_name[:-1]

    bar_name_markdown = f'*{util.escape_markdown_v2(bar_name_no_punctuation)}*'
    bar = bars.Bars(services.app.BAR_SPREADSHEET).match_bar(bar_name)
    if bar:
        link = f'https://www.google.com/maps/dir/?api=1&destination={bar.latitude},{bar.longitude}'
        bar_name_markdown = f'[{bar_name_markdown}]({link})'

    chat_id = app_settings.MAIN_CHAT_ID
    if app_settings.ANNOUNCEMENT_CHAT_ID:
        chat_id = app_settings.ANNOUNCEMENT_CHAT_ID
        message = f'The next bar night will be held at {bar_name_markdown}\\.\nEvent starts at 7:00pm and at full swing by 7:30pm'
    else:
        message = main_chat_message_func(bar_name_markdown)

    message_result = await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode='MarkdownV2',
        disable_web_page_preview=True,
        reply_to_message_id=reply_to_message_id if chat_id == app_settings.MAIN_CHAT_ID else None
    )

    # Only pin if main chat
    if chat_id == app_settings.MAIN_CHAT_ID:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_result.id)



EVENT_TYPE_ASK_FOR_SUGGESTIONS = 'AskForSuggestions'
EVENT_TYPE_CREATE_POLL = 'CreatePoll'
EVENT_TYPE_POLL_REMINDER = "PollReminder"
EVENT_TYPE_CHOOSE_WINNER = "ChooseWinner"

ScheduleCallable = Callable[[Dict[str, Any], SequenceServices], Awaitable[Dict[str, Any]]]

event_funcs: Dict[str, ScheduleCallable] = {
    EVENT_TYPE_ASK_FOR_SUGGESTIONS: handle_ask_for_suggestions,
    EVENT_TYPE_CREATE_POLL: handle_create_poll,
    EVENT_TYPE_POLL_REMINDER: handle_poll_reminder,
    EVENT_TYPE_CHOOSE_WINNER: handle_choose_winner
}
