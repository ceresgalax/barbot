import unittest
from datetime import datetime
from unittest.mock import AsyncMock, ANY, MagicMock

import telegram

from barbot import webhook
from barbot.database import Suggestion, ScheduledVenue
from barbot.app import AppSettings
from barbot.bars import Bars


class MockServices(object):
    def __init__(self):
        db = MagicMock()
        db.return_value.get_current_poll_id.return_value = 1
        self.db = db

        bot = MagicMock()
        bot.return_value.stop_poll = AsyncMock()
        bot.return_value.send_message = AsyncMock()
        bot.return_value.pin_chat_message = AsyncMock()
        bot.return_value.get_chat_member = AsyncMock()
        bot.return_value.set_message_reaction = AsyncMock()
        bot.return_value.edit_message_text = AsyncMock()
        bot.return_value.answer_callback_query = AsyncMock()
        self.bot = bot

        scheduler = MagicMock()
        self.scheduler = scheduler


class TestWebhookMessage(unittest.IsolatedAsyncioTestCase):
    async def test_reacts_with_success(self):
        mock_services = MockServices()
        app_settings = AppSettings({})
        bars = Bars(app_settings.BAR_SPREADSHEET)

        update = telegram.Update(
            update_id=1,
        )
        message = telegram.Message(
            message_id=2,
            date=datetime.utcnow(),
            text='Smuggler\'s Cove #barnight',
            chat=telegram.Chat(
                id=app_settings.MAIN_CHAT_ID,
                type=telegram.constants.ChatType.GROUP
            ),
            from_user=telegram.User(id=0, first_name='Ceres', is_bot=False)
        )

        await webhook.handle_message(update, message, mock_services.db(), mock_services.bot(), app_settings, bars)

        mock_services.bot.return_value.set_message_reaction.assert_called_with(
            chat_id=app_settings.MAIN_CHAT_ID,
            message_id=2,
            reaction=telegram.ReactionTypeEmoji(emoji="✍"),
            is_big=ANY
        )


OWNER_ID = 100
OTHER_ID = 200
SUGGESTION_UUID = 'a' * 32
EVENT_UUID = 'b' * 32


def make_member(status: str) -> MagicMock:
    member = MagicMock()
    member.status = status
    return member


def make_private_message(text: str, user_id: int) -> telegram.Message:
    return telegram.Message(
        message_id=5,
        date=datetime.utcnow(),
        text=text,
        chat=telegram.Chat(id=user_id, type=telegram.constants.ChatType.PRIVATE),
        from_user=telegram.User(id=user_id, first_name='Ceres', is_bot=False, username=f'user{user_id}')
    )


def make_callback_query(data: str, user_id: int) -> telegram.CallbackQuery:
    return telegram.CallbackQuery(
        id='q1',
        from_user=telegram.User(id=user_id, first_name='Ceres', is_bot=False, username=f'user{user_id}'),
        chat_instance='ci',
        data=data,
        message=make_private_message('Which suggestion do you want to delete?', user_id),
    )


class TestDeleteMenus(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        webhook.database.cached_membership.clear()
        self.services = MockServices()
        self.app = AppSettings({})
        self.bars = Bars(self.app.BAR_SPREADSHEET)
        self.db = self.services.db()
        self.bot = self.services.bot()
        self.bot.get_chat_member.return_value = make_member(telegram.ChatMember.MEMBER)
        self.suggestion = Suggestion(SUGGESTION_UUID, 'Smuggler\'s Cove', OWNER_ID, 'owner')
        self.db.get_current_suggestions.return_value = [
            self.suggestion,
            Suggestion('c' * 32, 'Other Bar', OTHER_ID, 'other'),
        ]
        self.db.get_suggestion_by_uuid.return_value = self.suggestion

    async def test_delete_shows_only_own_suggestions(self):
        await webhook.handle_message(telegram.Update(update_id=1), make_private_message('/delete', OWNER_ID),
                                     self.db, self.bot, self.app, self.bars)

        markup = self.bot.send_message.call_args.kwargs['reply_markup']
        callback_data = [row[0].callback_data for row in markup.inline_keyboard]
        self.assertEqual(callback_data, [f'del:{SUGGESTION_UUID}', 'del:cancel'])

    async def test_delete_without_suggestions_has_no_keyboard(self):
        self.db.get_current_suggestions.return_value = []
        await webhook.handle_message(telegram.Update(update_id=1), make_private_message('/delete', OWNER_ID),
                                     self.db, self.bot, self.app, self.bars)

        self.assertNotIn('reply_markup', self.bot.send_message.call_args.kwargs)

    async def test_owner_can_delete_via_button(self):
        query = make_callback_query(f'del:{SUGGESTION_UUID}', OWNER_ID)
        await webhook.handle_callback_query(telegram.Update(update_id=1), query, self.db, self.bot, self.app)

        self.db.remove_suggestion.assert_called_once_with(SUGGESTION_UUID)
        self.bot.send_message.assert_called_once_with(self.app.MAIN_CHAT_ID, ANY)
        self.bot.answer_callback_query.assert_called()

    async def test_non_owner_cannot_delete_via_button(self):
        query = make_callback_query(f'del:{SUGGESTION_UUID}', OTHER_ID)
        await webhook.handle_callback_query(telegram.Update(update_id=1), query, self.db, self.bot, self.app)

        self.db.remove_suggestion.assert_not_called()
        self.bot.answer_callback_query.assert_called()

    async def test_missing_suggestion(self):
        self.db.get_suggestion_by_uuid.return_value = None
        query = make_callback_query(f'del:{SUGGESTION_UUID}', OWNER_ID)
        await webhook.handle_callback_query(telegram.Update(update_id=1), query, self.db, self.bot, self.app)

        self.db.remove_suggestion.assert_not_called()
        self.bot.answer_callback_query.assert_called_with('q1', text='That suggestion no longer exists.')

    async def test_non_admin_cannot_delete_event(self):
        self.db.get_scheduled_venues.return_value = [ScheduledVenue(EVENT_UUID, 'Party', '0 19 ? * WED#4 *', 240)]
        query = make_callback_query(f'delev:{EVENT_UUID}', OWNER_ID)
        await webhook.handle_callback_query(telegram.Update(update_id=1), query, self.db, self.bot, self.app)

        self.db.remove_scheduled_venue.assert_not_called()

    async def test_admin_can_delete_event(self):
        self.bot.get_chat_member.return_value = make_member(telegram.ChatMember.ADMINISTRATOR)
        self.db.get_scheduled_venues.return_value = [ScheduledVenue(EVENT_UUID, 'Party', '0 19 ? * WED#4 *', 240)]
        query = make_callback_query(f'delev:{EVENT_UUID}', OWNER_ID)
        await webhook.handle_callback_query(telegram.Update(update_id=1), query, self.db, self.bot, self.app)

        self.db.remove_scheduled_venue.assert_called_once_with(EVENT_UUID)
