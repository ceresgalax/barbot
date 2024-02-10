import difflib
import json
import re
import sys
import traceback
import urllib.parse
import uuid
from typing import Dict, Any, Optional

import telegram

from . import database, app, util, bars, geo

bot = telegram.Bot(
    token=app.TELEGRAM_BOT_TOKEN
)

BARS = bars.Bars(app.BAR_SPREADSHEET)


def error(message: str):
    sys.stderr.write(message)
    sys.stderr.write('\n')
    sys.stderr.flush()


def handle_webhook(event: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    body_json = event['body']
    body = json.loads(body_json)
    result = app.asyncio_loop.run_until_complete(handle_webhook_async(body))

    if result:
        return result

    return {}


async def handle_webhook_async(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    print(f'Received webhook! {body}')

    update = telegram.Update.de_json(body, bot)
    if not update:
        error('Failed to parse Update body')
        return

    if update.inline_query is not None:
        return await handle_inline_query(update, update.inline_query)

    if update.message is not None:
        await handle_message(update, update.message)


async def handle_inline_query(udpate: telegram.Update, query: telegram.InlineQuery) -> Optional[Dict[str, Any]]:
    # Make sure the user is part of the chatroom
    is_member = await database.is_user_part_of_main_chat(bot, user_id=query.from_user.id)

    query_text = query.query
    answers = []
    if query_text and is_member:
        current_suggestions = database.get_current_suggestions()
        possibilities = [x.venue for x in current_suggestions]
        suggestions_by_name = {s.venue: s for s in current_suggestions}
        matches = difflib.get_close_matches(query_text, possibilities, n=5, cutoff=0.1)

        def make_result(hex_uuid: str, match_name: str) -> Dict[str, Any]:
            return {
                'type': 'article',
                'id': hex_uuid,
                'title': match_name,
                'input_message_content': {
                    'message_text': f'{match_name} {app.BARNIGHT_HASHTAG}'
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


async def add_suggestion(venue: str, user_id: int, username: str) -> None:
    venue = re.sub(r'\s+', ' ', venue).strip().lower().capitalize()
    venue = re.sub(r'\s\S', lambda m: m.group(0).title(), venue)

    if len(venue) < app.MIN_VENUE_LENGTH:
        return
    if len(venue) > app.MAX_VENUE_LENGTH:
        await bot.send_message(
            app.MAIN_CHAT_ID,
            f'Sorry @{username}, venue suggestions must be between {app.MIN_VENUE_LENGTH} and {app.MAX_VENUE_LENGTH} '
            f'characters long.'
        )
        return

    # try to use the canonical name of the bar (if we can find one)
    bar = BARS.match_bar(venue)
    venue = bar.name if bar else venue

    suggestions = database.get_current_suggestions(bypass_cache=True)

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
            text=f'@{username} has suggested "{venue}" for {app.BARNIGHT_HASHTAG}, '
                 f'which was already suggested by {found_suggestion.user_handle}'
        )
    else:

        if len(suggestions) >= app.MAX_SUGGESTIONS:
            await bot.send_message(
                chat_id=app.MAIN_CHAT_ID,
                text=f'Sorry, I could not add @{username}\'s suggestion for "{venue}" since we have hit the max number '
                     f'of suggestions for the next poll ({app.MAX_SUGGESTIONS}).'
            )
        else:
            venue_uuid = uuid.uuid4().hex
            try:
                database.add_suggestion(venue_uuid, venue, user_id, username)
            except:
                traceback.print_exc()
                await bot.send_message(
                    app.MAIN_CHAT_ID,
                    f'Sorry @{username}, I was unable to add your suggestion for "{venue}". Please try again.'
                )
                return

            text = venue
            if bar:
                link = f'https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(venue + ", " + bar.address)}'
                text = f'[{text}]({link})'

            # Send message to the main chat to let people know that a suggestion was added.
            await bot.send_message(
                chat_id=app.MAIN_CHAT_ID,
                text=f'@{username} has successfully suggested "{text}" for the next {util.escape_markdown_v2(app.BARNIGHT_HASHTAG)} poll\!',
                parse_mode='MarkdownV2',
                disable_web_page_preview=True,
            )


async def handle_message(update: telegram.Update, message: telegram.Message):
    # Don't accept input from other bots.
    if message.from_user.is_bot:
        return

    # Only accept messages with text.
    if not message.text:
        return

    is_admin = await database.is_user_admin_of_main_chat(bot, message.from_user.id)

    message_lower = message.text.lower()

    if message.chat.type == telegram.Chat.PRIVATE:
        if message_lower.startswith('/start'):
            message_text = f'Hello there! You can use me to suggest venues for bar night!\n\n' \
                    f'To suggest a venue, send a message to the main chatroom with the hashtag #barnight. ' \
                    f'You can also use @{app.BOT_USERNAME} in your message to suggest a venue.'
            await bot.send_message(message.chat.id, message_text)

        elif message_lower.startswith('/delete ') or message_lower == '/delete':
            venue_name = message.text[len('/delete '):].strip()
            if not venue_name:
                await bot.send_message(
                    message.chat.id,
                    'Usage: /delete <venue_name>'
                )
            else:
                suggestions = database.get_current_suggestions(bypass_cache=False)
                suggestion = next((s for s in suggestions if s.venue.lower() == venue_name.lower()), None)
                if suggestion:
                    if is_admin or message.from_user.id == suggestion.user_id:
                        try:
                            database.remove_suggestion(suggestion.uuid)
                        except:
                            await bot.send_message(
                                message.chat.id,
                                f'Was unable to remove suggestion "{venue_name}" :('
                            )
                            traceback.print_exc()
                            return
                        await bot.send_message(
                            message.chat.id,
                            f'Successfully removed "{venue_name}" from suggestions.'
                        )
                        await bot.send_message(
                            app.MAIN_CHAT_ID,
                            f'@{message.from_user.username} has removed @{suggestion.user_handle}\'s suggestion for '
                            f'"{suggestion.venue}"'
                        )
                    else:
                        await bot.send_message(
                            message.chat.id,
                            'Sorry, you can only delete venues that you suggested. '
                            '(Only admins can delete any suggestion)'
                        )
                else:
                    await bot.send_message(
                        message.chat.id,
                        f'Could not find suggestion "{venue_name}" to remove.'
                    )

        elif message_lower.startswith('/list') or message_lower == '/list':
            if await database.is_user_part_of_main_chat(bot, message.from_user.id):
                suggestions = database.get_current_suggestions()
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
                    BARS, database.get_current_suggestions(bypass_cache=False),
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

        elif app.BARNIGHT_HASHTAG in message_lower:
            await bot.send_message(
                message.chat.id,
                f'Please send venue suggestions in the main chatroom.',
                reply_to_message_id=message.id,
            )

    elif message.chat.id == app.MAIN_CHAT_ID:
        hashtag_index = message_lower.find(app.BARNIGHT_HASHTAG)
        if hashtag_index != -1:
            left_of_hashtag = message.text[0:hashtag_index].strip()
            right_of_hashtag = message.text[hashtag_index+len(app.BARNIGHT_HASHTAG):].strip()
            if len(left_of_hashtag) > 0 and len(right_of_hashtag) > 0 \
                    or len(left_of_hashtag) == 0 and len(right_of_hashtag) == 0:
                pass
            else:
                suggestion_text = left_of_hashtag if len(left_of_hashtag) > len(right_of_hashtag) else right_of_hashtag
                await add_suggestion(suggestion_text, message.from_user.id, message.from_user.username)
