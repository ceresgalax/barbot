import unittest
from typing import Sequence
from unittest.mock import AsyncMock, ANY, MagicMock

import telegram

from barbot import sequence
from barbot.app import AppSettings
from barbot.sequence import SequenceServices


class MockServices(object):
    def __init__(self):
        db = MagicMock()
        db.return_value.get_current_poll_id.return_value = 1
        self.db = db

        bot = MagicMock()
        bot.return_value.stop_poll = AsyncMock()
        bot.return_value.send_message = AsyncMock()
        bot.return_value.pin_chat_message = AsyncMock()
        self.bot = bot

        scheduler = MagicMock()
        self.scheduler = scheduler

        self.app_settings = AppSettings({})

    def configure_stop_poll(self, options: Sequence[telegram.PollOption]):
        self.bot.return_value.stop_poll.return_value = telegram.Poll(
            id='1',
            question='',
            options=options,
            total_voter_count=0,
            is_closed=True,
            is_anonymous=False,
            type='',
            allows_multiple_answers=True
        )

    def make_services(self) -> SequenceServices:
        return SequenceServices(self.db(), self.bot(), self.scheduler(), self.app_settings)


class TestChooseWinner(unittest.IsolatedAsyncioTestCase):
    async def test_typical_bar(self):
        mock_services = MockServices()
        mock_services.configure_stop_poll([
            telegram.PollOption('Foo', 5),
            telegram.PollOption('Bar', 6),  # pun intended
        ])

        result = await sequence.handle_choose_winner({}, mock_services.make_services())

        expected_message = 'Calling it for *Bar*\\!'
        mock_services.bot.return_value.send_message.assert_called_with(
            chat_id=ANY, text=expected_message, parse_mode='MarkdownV2',
            disable_web_page_preview=ANY, reply_to_message_id=ANY)

    async def test_bar_with_markdown_characters(self):
        mock_services = MockServices()
        mock_services.configure_stop_poll([
            telegram.PollOption('Foo', 5),
            telegram.PollOption('Din.gles', 6),
        ])

        result = await sequence.handle_choose_winner({}, mock_services.make_services())
        expected_message = 'Calling it for *Din\\.gles*\\!'
        mock_services.bot.return_value.send_message.assert_called_with(
            chat_id=ANY, text=expected_message, parse_mode='MarkdownV2',
            disable_web_page_preview=ANY, reply_to_message_id=ANY)

    async def test_bar_ending_with_punctuation(self):
        punctuation_marks = ['.', '!', '?']
        for punctuation_mark in punctuation_marks:
            mock_services = MockServices()
            mock_services.configure_stop_poll([
                telegram.PollOption('Foo', 5),
                telegram.PollOption(f'Dingles{punctuation_mark}', 6),
            ])

            result = await sequence.handle_choose_winner({}, mock_services.make_services())
            expected_message = 'Calling it for *Dingles*\\!'
            mock_services.bot.return_value.send_message.assert_called_with(
                chat_id=ANY, text=expected_message, parse_mode='MarkdownV2',
                disable_web_page_preview=ANY, reply_to_message_id=ANY)

    async def test_result_sent_to_associated_channel(self):
        mock_services = MockServices()
        mock_services.configure_stop_poll([
            telegram.PollOption('Foo', 5),
            telegram.PollOption(f'Dingles', 6),
        ])
        mock_services.app_settings.MAIN_CHAT_ID = 12345
        mock_services.app_settings.ANNOUNCEMENT_CHAT_ID = 67890

        result = await sequence.handle_choose_winner({}, mock_services.make_services())

        expected_message = 'The next bar night will be held at Dingles\\.'
        mock_services.bot.return_value.send_message.assert_called_with(
            chat_id=mock_services.app_settings.ANNOUNCEMENT_CHAT_ID, text=ANY, parse_mode=ANY,
            disable_web_page_preview=ANY, reply_to_message_id=ANY)
        mock_services.bot.return_value.pin_chat_message.assert_not_called()


    async def test_result_sent_to_main_group_if_associated_channel_not_set(self):
        mock_services = MockServices()
        mock_services.configure_stop_poll([
            telegram.PollOption('Foo', 5),
            telegram.PollOption(f'Dingles', 6),
        ])
        mock_services.app_settings.MAIN_CHAT_ID = 12345

        result = await sequence.handle_choose_winner({}, mock_services.make_services())

        expected_message = 'Calling it for *Dingles*\\!'
        mock_services.bot.return_value.send_message.assert_called_with(
            chat_id=mock_services.app_settings.MAIN_CHAT_ID, text=expected_message, parse_mode=ANY,
            disable_web_page_preview=ANY, reply_to_message_id=ANY)
        mock_services.bot.return_value.pin_chat_message.assert_called_with(
            chat_id=mock_services.app_settings.MAIN_CHAT_ID, message_id=ANY)
