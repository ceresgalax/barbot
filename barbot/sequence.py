"""
Lambda functions intended to be called from Step Functions go here
"""
import random
import traceback
from typing import Dict, Any, List

import telegram

from . import app, bars, database, util, schedule_util

bot = telegram.Bot(
    token=app.TELEGRAM_BOT_TOKEN
)


def handle_function_call(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    event_type = event['barnight_event_type']
    func = event_funcs[event_type]
    return app.asyncio_loop.run_until_complete(func(event))


async def handle_ask_for_suggestions(event: Dict[str, Any]) -> Dict[str, Any]:
    # if schedule_util.is_fourth_tuesday_tomorrow():
    #     text = 'El Rio this week!'
    #     await bot.send_message(chat_id=app.MAIN_CHAT_ID, text=text)
    #     return {}

    text = f'It\'s time for bar night suggestions! Message @{app.BOT_USERNAME} or end a message with ' \
           f'{app.BARNIGHT_HASHTAG} to input a suggestion!'
    poll_time = schedule_util.get_schedule_time(app.CREATE_POLL_SCHEDULE_NAME)
    if poll_time:
        text += f' Poll will be created on {poll_time}.'

    await bot.send_message(chat_id=app.MAIN_CHAT_ID, text=text)
    return {}


async def handle_create_poll(event: Dict[str, Any]) -> Dict[str, Any]:
    database.set_current_poll_id(0)
    suggestions = database.get_current_suggestions(bypass_cache=True)

    if len(suggestions) == 0:
        send_message_result = await bot.send_message(
            chat_id=app.MAIN_CHAT_ID,
            text='Oops! No one suggested anything for barnight. I\'m gonna sit this one out...',
        )
    elif len(suggestions) == 1:
        send_message_result = await bot.send_message(
            chat_id=app.MAIN_CHAT_ID,
            text=f'There was only one suggestion, and it was for {suggestions[0].venue}.'
        )
        await bot.pin_chat_message(chat_id=app.MAIN_CHAT_ID, message_id=send_message_result.id)
    else:
        try:
            png, png_text = await util.get_map_suggestions_message_data(bars.Bars(app.BAR_SPREADSHEET), suggestions)
            if png:
                await bot.send_photo(
                    app.MAIN_CHAT_ID,
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
                chat_id=app.MAIN_CHAT_ID,
                question='Where are we going for barnight? (multiple choice)',
                options=[x.venue for x in suggestions],
                is_anonymous=False,
                type='regular',
                allows_multiple_answers=True
            )
        except:
            traceback.print_exc()
            error_message_result = await bot.send_message(
                app.MAIN_CHAT_ID,
                'Oh no! I was unable to create a poll for barnight! Please continue the process manually. '
                'Here is the list of suggested venues:\n\n'
                + util.get_list_suggestions_message_text(database.get_current_suggestions(bypass_cache=True))
            )
            database.clear_suggestions()
            await bot.pin_chat_message(chat_id=app.MAIN_CHAT_ID, message_id=error_message_result.message_id)
            return {}

        poll_id = send_poll_result.id
        database.set_current_poll_id(poll_id)
        await bot.pin_chat_message(chat_id=app.MAIN_CHAT_ID, message_id=poll_id)

    # TODO: if `bot.pin_chat_message` fails, this will never be called,
    # which means we'll re-use the suggestions next round
    database.clear_suggestions()
    return {}


async def handle_poll_reminder(event: Dict[str, Any]) -> Dict[str, Any]:
    poll_id = database.get_current_poll_id()
    if not poll_id:
        return {}

    text = "REMINDER: Don't forget to vote!"
    close_time = schedule_util.get_schedule_time(app.CLOSE_POLL_SCHEDULE_NAME)
    if close_time:
        text += f' The poll will close on {close_time}.'

    await bot.send_message(
        chat_id=app.MAIN_CHAT_ID,
        text=text,
        reply_to_message_id=poll_id
    )
    return {}


async def handle_choose_winner(event: Dict[str, Any]) -> Dict[str, Any]:
    poll_id = database.get_current_poll_id()

    if not poll_id:
        return {}

    try:
        poll = await bot.stop_poll(
            chat_id=app.MAIN_CHAT_ID,
            message_id=poll_id
        )
    except:
        traceback.print_exc()
        error_message_result = await bot.send_message(
            app.MAIN_CHAT_ID,
            'Oh no! I was unable to close the poll for barnight! '
            'Please close the poll (if it wasn\'t closed already) and declare a winner for me.'
        )
        database.set_current_poll_id(0)
        await bot.pin_chat_message(chat_id=app.MAIN_CHAT_ID, message_id=error_message_result.message_id)
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

    text = f'*{util.escape_markdown_v2(chosen_option.text)}*'
    bar = bars.Bars(app.BAR_SPREADSHEET).match_bar(chosen_option.text)
    if bar:
        link = f'https://www.google.com/maps/dir/?api=1&destination={bar.latitude},{bar.longitude}'
        text = f'[{text}]({link})'
    message = f'Calling it for {text}\\!'
    if len(top_options) > 1:
        message += f' \\(Chosen randomly out of the top {len(top_options)} options\\)'

    message_result = await bot.send_message(
        chat_id=app.MAIN_CHAT_ID,
        text=message,
        parse_mode='MarkdownV2',
        disable_web_page_preview=True,
        reply_to_message_id=poll_id
    )

    await bot.pin_chat_message(
        chat_id=app.MAIN_CHAT_ID,
        message_id=message_result.id,
    )

    database.set_current_poll_id(0)
    return {}


EVENT_TYPE_ASK_FOR_SUGGESTIONS = 'AskForSuggestions'
EVENT_TYPE_CREATE_POLL = 'CreatePoll'
EVENT_TYPE_POLL_REMINDER = "PollReminder"
EVENT_TYPE_CHOOSE_WINNER = "ChooseWinner"

event_funcs = {
    EVENT_TYPE_ASK_FOR_SUGGESTIONS: handle_ask_for_suggestions,
    EVENT_TYPE_CREATE_POLL: handle_create_poll,
    EVENT_TYPE_POLL_REMINDER: handle_poll_reminder,
    EVENT_TYPE_CHOOSE_WINNER: handle_choose_winner
}
