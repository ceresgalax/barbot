import asyncio
import os


MAIN_CHAT_ID = int(os.environ.get('MAIN_CHAT_ID', '0'))
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_SECRET = os.environ.get('TELEGRAM_BOT_API_SECRET_TOKEN')
DYNAMODB_ENDPOINT_URL = os.environ.get('DYNAMODB_ENDPOINT_URL')
DYNAMO_WEEK_TABLE_NAME = os.environ.get('DYNAMO_WEEK_TABLE_NAME')
BOT_USERNAME = os.environ.get('BOT_USERNAME')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
SCHEDULE_GROUP_NAME = os.environ.get('SCHEDULE_GROUP_NAME', '')
CREATE_POLL_SCHEDULE_NAME = os.environ.get('CREATE_POLL_SCHEDULE_NAME', '')
CLOSE_POLL_SCHEDULE_NAME = os.environ.get('CLOSE_POLL_SCHEDULE_NAME', '')
BAR_SPREADSHEET = os.environ.get('BAR_SPREADSHEET', '')
SELENIUM_SERVER_URL = os.environ.get('SELENIUM_SERVER_URL', 'http://localhost:4444')

BARNIGHT_HASHTAG = '#barnight'

# This limit is imposed by the max number of poll options in a Telegram poll.\
# Change this if Telegram's limit changes in the future.
MAX_SUGGESTIONS = 10
MIN_VENUE_LENGTH = 1
MAX_VENUE_LENGTH = 100

asyncio_loop = asyncio.get_event_loop()
