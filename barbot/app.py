import asyncio
import os


MAIN_CHAT_ID = int(os.environ.get('MAIN_CHAT_ID', '0'))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_SECRET = os.environ.get('TELEGRAM_BOT_API_SECRET_TOKEN')
DYNAMO_WEEK_TABLE_NAME = os.environ.get('DYNAMO_WEEK_TABLE_NAME')
BOT_USERNAME = os.environ.get('BOT_USERNAME')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')

BARNIGHT_HASHTAG = '#barnight'

# This limit is imposed by the max number of poll options in a Telegram poll.\
# Change this if Telegram's limit changes in the future.
MAX_SUGGESTIONS = 10
MIN_VENUE_LENGTH = 1
MAX_VENUE_LENGTH = 100

asyncio_loop = asyncio.get_event_loop()
