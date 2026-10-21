import difflib
import json
import os
import re
import sys
import traceback
import urllib.parse
import uuid
from typing import Dict, Any, Optional

import telegram

from . import database, util
from .app import AppSettings, MIN_VENUE_LENGTH, MAX_VENUE_LENGTH, BARNIGHT_HASHTAG, MAX_SUGGESTIONS, asyncio_loop
from .bars import Bars
from .database import Database


DELETE_SUGGESTION_PREFIX = 'del:'
DELETE_EVENT_PREFIX = 'delev:'
CANCEL = 'cancel'


def error(message: str):
    sys.stderr.write(message)
    sys.stderr.write('\n')
    sys.stderr.flush()

# This is the entry point for the webhook lambda function from AWS API gateway.
def handle_webhook(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    body_json = event['body']
    body = json.loads(body_json)
    result = asyncio_loop.run_until_complete(handle_webhook_async(body))

    if result:
        return result

    return {}


async def handle_webhook_async(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    print(f'Received webhook! {body}')

    app_settings = AppSettings(os.environ)

    assert app_settings.TELEGRAM_BOT_TOKEN is not None
    bot = telegram.Bot(
        token=app_settings.TELEGRAM_BOT_TOKEN
    )

    db = database.DynamoDatabase(app_settings)

    bars = Bars(app_settings.BAR_SPREADSHEET)

    update = telegram.Update.de_json(body, bot)
    if not update:
        error('Failed to parse Update body')
        return None

    if update.inline_query is not None:
        return await handle_inline_query(update, update.inline_query, db, bot, app_settings)

    if update.message is not None:
        await handle_message(update, update.message, db, bot, app_settings, bars)
        return None

    if update.callback_query is not None:
        await handle_callback_query(update, update.callback_query, db, bot, app_settings)
        return None

    return None


async def handle_inline_query(update: telegram.Update, query: telegram.InlineQuery, db: Database, bot: telegram.Bot, app: AppSettings) -> Optional[Dict[str, Any]]:
    # Make sure the user is part of the chatroom
    is_member = await database.is_user_part_of_main_chat(bot, app, user_id=query.from_user.id)

    query_text = query.query
    answers = []
    if query_text and is_member:
        current_suggestions = db.get_current_suggestions()
        possibilities = [x.venue for x in current_suggestions]
        suggestions_by_name = {s.venue: s for s in current_suggestions}
        matches = difflib.get_close_matches(query_text, possibilities, n=5, cutoff=0.1)

        def make_result(hex_uuid: str, match_name: str) -> Dict[str, Any]:
            return {
                'type': 'article',
                'id': hex_uuid,
                'title': match_name,
                'input_message_content': {
                    'message_text': f'{match_name} {BARNIGHT_HASHTAG}'
                }
            }

        if query_text not in suggestions_by_name:
            answers.append(make_result('null', query_text))
        answers.extend(make_result(suggestions_by_name[x].uuid, x) for x in matches)

    print(f'returning {len(answers)} answers')

    return {
        'method': 'answerInlineQuery',
        'inline_query_id': query.id,
        'results': answers,
        'cache_time': 60,
        'is_personal': True  # Needs to be personal so that we don't leak suggestions to non-members.
    }


async def handle_callback_query(update: telegram.Update, query: telegram.CallbackQuery, db: Database, bot: telegram.Bot, app: AppSettings) -> None:
    data = query.data or ''
    chat_id = query.message.chat.id if query.message else None
    message_id = query.message.message_id if query.message else None

    async def finish(message_text: str, answer_text: Optional[str] = None) -> None:
        # Replace the keyboard message with the outcome so the buttons can't be tapped again.
        if chat_id is not None and message_id is not None:
            await bot.edit_message_text(message_text, chat_id=chat_id, message_id=message_id)
        await bot.answer_callback_query(query.id, text=answer_text)

    if data.startswith(DELETE_SUGGESTION_PREFIX):
        suggestion_uuid = data[len(DELETE_SUGGESTION_PREFIX):]
        if suggestion_uuid == CANCEL:
            await finish('Cancelled.')
            return

        suggestion = db.get_suggestion_by_uuid(suggestion_uuid)
        if suggestion is None:
            await finish('That suggestion no longer exists.', 'That suggestion no longer exists.')
            return

        is_admin = await database.is_user_admin_of_main_chat(bot, app, query.from_user.id)
        if not is_admin and query.from_user.id != suggestion.user_id:
            await bot.answer_callback_query(
                query.id,
                text='Sorry, you can only delete venues that you suggested.',
                show_alert=True
            )
            return

        try:
            db.remove_suggestion(suggestion.uuid)
        except:
            traceback.print_exc()
            await bot.answer_callback_query(query.id, text=f'Was unable to remove "{suggestion.venue}" :(', show_alert=True)
            return

        await finish(f'Deleted "{suggestion.venue}".')
        await bot.send_message(
            app.MAIN_CHAT_ID,
            f'@{query.from_user.username} has removed @{suggestion.user_handle}\'s suggestion for '
            f'"{suggestion.venue}"'
        )

    elif data.startswith(DELETE_EVENT_PREFIX):
        event_uuid = data[len(DELETE_EVENT_PREFIX):]
        if event_uuid == CANCEL:
            await finish('Cancelled.')
            return

        if not await database.is_user_admin_of_main_chat(bot, app, query.from_user.id):
            await bot.answer_callback_query(query.id, text='You must be an admin to delete events.', show_alert=True)
            return

        event = next((e for e in db.get_scheduled_venues() if e.uuid == event_uuid), None)
        if event is None:
            await finish('That scheduled event no longer exists.', 'That scheduled event no longer exists.')
            return

        try:
            db.remove_scheduled_venue(event.uuid)
        except:
            traceback.print_exc()
            await bot.answer_callback_query(query.id, text='Sorry, I had trouble deleting the scheduled event.', show_alert=True)
            return

        await finish(f'Deleted scheduled event "{event.venue_name}".')

    else:
        await bot.answer_callback_query(query.id)


async def add_suggestion(venue: str, user_id: int, username: str, message_id: int, db: Database, bot: telegram.Bot, app: AppSettings, bars: Bars) -> None:
    venue = re.sub(r'\s+', ' ', venue).strip().lower().capitalize()
    venue = re.sub(r'\s\S', lambda m: m.group(0).title(), venue)

    if len(venue) < MIN_VENUE_LENGTH:
        return
    if len(venue) > MAX_VENUE_LENGTH:
        await bot.send_message(
            app.MAIN_CHAT_ID,
            f'Sorry @{username}, venue suggestions must be between {MIN_VENUE_LENGTH} and {MAX_VENUE_LENGTH} '
            f'characters long.'
        )
        return

    # try to use the canonical name of the bar (if we can find one)
    bar = bars.match_bar(venue)
    venue = bar.name if bar else venue

    suggestions = db.get_current_suggestions(bypass_cache=True)

    found_suggestion: Optional[database.Suggestion] = None

    normalized_venue = [c.lower() for c in venue if c.isalpha()]

    for suggestion in suggestions:
        normalized_suggestion_venue = [c.lower() for c in suggestion.venue if c.isalpha()]
        if normalized_venue == normalized_suggestion_venue:
            found_suggestion = suggestion
            break

    if found_suggestion is not None:
        await bot.send_message(
            chat_id=app.MAIN_CHAT_ID,
            text=f'@{username} has suggested "{venue}" for {BARNIGHT_HASHTAG}, '
                 f'which was already suggested by {found_suggestion.user_handle}'
        )
    else:
        if len(suggestions) >= MAX_SUGGESTIONS:
            await bot.send_message(
                chat_id=app.MAIN_CHAT_ID,
                text=f'Sorry, I could not add @{username}\'s suggestion for "{venue}" since we have hit the max number '
                     f'of suggestions for the next poll ({MAX_SUGGESTIONS}).'
            )
        else:
            venue_uuid = uuid.uuid4().hex
            try:
                db.add_suggestion(venue_uuid, venue, user_id, username)
            except:
                traceback.print_exc()
                await bot.send_message(
                    app.MAIN_CHAT_ID,
                    f'Sorry @{username}, I was unable to add your suggestion for "{venue}". Please try again.'
                )
                return

            venue_markdown = util.escape_markdown_v2(venue)
            if bar:
                link = f'https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(venue + ", " + bar.address)}'
                venue_markdown = f'[{venue_markdown}]({link})'

            # Send message to the main chat to let people know that a suggestion was added.
            await bot.set_message_reaction(
                chat_id=app.MAIN_CHAT_ID,
                message_id=message_id,
                reaction=telegram.ReactionTypeEmoji(emoji='✍'),
                is_big=False
            )


async def handle_message(update: telegram.Update, message: telegram.Message, db: Database, bot: telegram.Bot, app: AppSettings, bars: Bars) -> None:
    # Can't do anything if we don't know who sent this message.
    if message.from_user is None:
        return

    # Don't accept input from other bots.
    if message.from_user.is_bot:
        return

    # Only accept messages with text.
    if not message.text:
        return

    is_admin = await database.is_user_admin_of_main_chat(bot, app, message.from_user.id)

    message_lower = message.text.lower()

    if message.chat.type == telegram.Chat.PRIVATE:
        if message_lower.startswith('/start'):
            message_text = f'Hello there! You can use me to suggest venues for bar night!\n\n' \
                    f'To suggest a venue, send a message to the main chatroom with the hashtag #barnight. ' \
                    f'You can also use @{app.BOT_USERNAME} in your message to suggest a venue.'
            await bot.send_message(message.chat.id, message_text)

        elif message_lower.startswith('/delete'):
            suggestions = db.get_current_suggestions(bypass_cache=True)
            if not is_admin:
                suggestions = [s for s in suggestions if s.user_id == message.from_user.id]
            if not suggestions:
                await bot.send_message(
                    message.chat.id,
                    'There are no suggestions to delete.' if is_admin else
                    "You don't have any suggestions to delete."
                )
            else:
                buttons = [
                    [telegram.InlineKeyboardButton(
                        f'{s.venue} — @{s.user_handle}' if is_admin else s.venue,
                        callback_data=f'{DELETE_SUGGESTION_PREFIX}{s.uuid}'
                    )]
                    for s in suggestions
                ]
                buttons.append([telegram.InlineKeyboardButton('Cancel', callback_data=f'{DELETE_SUGGESTION_PREFIX}{CANCEL}')])
                await bot.send_message(
                    message.chat.id,
                    'Which suggestion do you want to delete?',
                    reply_markup=telegram.InlineKeyboardMarkup(buttons)
                )

        elif message_lower.startswith('/list') or message_lower == '/list':
            if await database.is_user_part_of_main_chat(bot, app, message.from_user.id):
                suggestions = db.get_current_suggestions()
                message_text = 'Current suggested venues:\n\n'
                message_text += util.get_list_suggestions_message_text(suggestions)
                await bot.send_message(message.chat.id, message_text)
            else:
                await bot.send_message(
                    message.chat.id,
                    'You must be a member of the main chatroom to list suggestions.'
                )

        elif message_lower.startswith('/map'):
            temp_message = await bot.send_message(
                message.chat.id,
                'One sec, let me get you a map of the current suggestions...',
                reply_to_message_id=message.id,
            )
            try:
                png, message_text = await util.get_map_suggestions_message_data(
                    bars, db.get_current_suggestions(bypass_cache=False), app
                )
            except Exception as err:
                print(f'Map rendering failed: {err}')
                await bot.send_message(
                    message.chat.id,
                    "Sorry: We're having some trouble generate maps right now.",
                    reply_to_message_id=message.id,
                )
            else:
                if png:
                    await bot.send_photo(
                        message.chat.id,
                        png,
                        message_text,
                        parse_mode='MarkdownV2',
                        reply_to_message_id=message.id,
                    )
                else:
                    await bot.send_message(
                        message.chat.id,
                        "There aren't any suggested bars that we can map.",
                        reply_to_message_id=message.id,
                    )
            finally:
                try:
                    await bot.delete_message(message.chat.id, temp_message.message_id)
                except:
                    pass

        elif message_lower.startswith('/newevent'):
            json_body = message.text[len('/newevent '):].strip()
            if not is_admin:
                await bot.send_message(message.chat.id, 'You must be an admin to use this command.')
            elif not json_body:
                message_text = \
                    'Usage: /newevent \\<json\\>\n\n' \
                    'The message should look something like this:\n' \
                    '```\n' \
                    '/newevent {\n' \
                    '    "venue_name": "NAME",\n' \
                    '    "cron": "0 19 ? * WED#4 *",\n' \
                    '    "duration_minutes": 240\n' \
                    '}\n' \
                    '```'
                await bot.send_message(message.chat.id, message_text, parse_mode='MarkdownV2')
            else:
                try:
                    data = json.loads(json_body)
                    event_uuid = uuid.uuid4().hex
                    db.add_scheduled_venue(event_uuid, str(data['venue_name']), str(data['cron']), int(data['duration_minutes']))
                except:
                    traceback.print_exc()
                    await bot.send_message(message.chat.id, 'Sorry, I had trouble parsing that json.')
                    return

                await bot.send_message(message.chat.id, 'Event created!')

        elif message_lower.startswith('/delevent'):
            if not is_admin:
                await bot.send_message(message.chat.id, 'You must be an admin to use this command.')
            else:
                events = db.get_scheduled_venues()
                if not events:
                    await bot.send_message(message.chat.id, 'There are no scheduled events to delete.')
                else:
                    buttons = [
                        [telegram.InlineKeyboardButton(e.venue_name, callback_data=f'{DELETE_EVENT_PREFIX}{e.uuid}')]
                        for e in events
                    ]
                    buttons.append([telegram.InlineKeyboardButton('Cancel', callback_data=f'{DELETE_EVENT_PREFIX}{CANCEL}')])
                    await bot.send_message(
                        message.chat.id,
                        'Which scheduled event do you want to delete?',
                        reply_markup=telegram.InlineKeyboardMarkup(buttons)
                    )

        elif BARNIGHT_HASHTAG in message_lower:
            await bot.send_message(
                message.chat.id,
                f'Please send venue suggestions in the main chatroom.',
                reply_to_message_id=message.id,
            )

    elif message.chat.id == app.MAIN_CHAT_ID:
        hashtag_index = message_lower.find(BARNIGHT_HASHTAG)
        if hashtag_index != -1:
            left_of_hashtag = message.text[0:hashtag_index].strip()
            right_of_hashtag = message.text[hashtag_index+len(BARNIGHT_HASHTAG):].strip()
            if len(left_of_hashtag) > 0 and len(right_of_hashtag) > 0 \
                    or len(left_of_hashtag) == 0 and len(right_of_hashtag) == 0:
                pass
            else:
                suggestion_text = left_of_hashtag if len(left_of_hashtag) > len(right_of_hashtag) else right_of_hashtag
                await add_suggestion(suggestion_text, message.from_user.id, message.from_user.username or 'unknown', message.id, db, bot, app, bars)
