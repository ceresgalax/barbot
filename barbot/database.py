import datetime
from typing import List, Optional, Dict, Any, Tuple

import boto3
import telegram

from . import app


CACHE_TTL = datetime.timedelta(seconds=3)


class Suggestion(object):
    def __init__(self, hex_uuid: str, venue: str, user_id: int, user_handle: str):
        self.uuid = hex_uuid
        self.venue = venue
        self.user_id = user_id
        self.user_handle = user_handle


last_suggestions_update_time = datetime.datetime(day=1, month=1, year=1)
cached_suggestions: List[Suggestion] = []

if app.DYNAMODB_ENDPOINT_URL:
    dynamodb = boto3.client('dynamodb', endpoint_url=app.DYNAMODB_ENDPOINT_URL)
else:
    dynamodb = boto3.client('dynamodb')


def get_current_poll_id() -> Optional[int]:
    result = dynamodb.get_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
        ConsistentRead=True
    )
    item = result.get('Item', {})
    return int(item.get('poll_id', {}).get('N', 0))


def set_current_poll_id(poll_id: int) -> None:
    dynamodb.update_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
        UpdateExpression='SET poll_id = :p',
        ExpressionAttributeValues={
            ':p': {'N': str(poll_id)}
        }
    )


def make_suggestion(k: str, v: Dict[str, Any]) -> Suggestion:
    m = v['M']
    return Suggestion(k, m['name']['S'], int(m['user_id']['N']), m['user_handle']['S'])


def get_current_suggestions(bypass_cache=False) -> List[Suggestion]:
    global cached_suggestions
    global last_suggestions_update_time
    now = datetime.datetime.utcnow()
    if not bypass_cache and now < last_suggestions_update_time + CACHE_TTL:
        return cached_suggestions

    get_result = dynamodb.get_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}}
    )
    item = get_result.get('Item')
    if not item:
        return []
    suggestions_map = item['venues']['M']
    suggestions = [make_suggestion(k, v) for k, v in suggestions_map.items()]
    cached_suggestions = suggestions
    last_suggestions_update_time = now
    return suggestions


def get_suggestion_by_uuid(hex_uuid: str) -> Optional[Suggestion]:
    get_result = dynamodb.get_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
    )
    venue_data = get_result.get('Item', {}).get('venues', {}).get('M', {}).get(hex_uuid)
    if not venue_data:
        return None
    return make_suggestion(hex_uuid, venue_data)


def clear_suggestions() -> None:
    global cached_suggestions
    global last_suggestions_update_time
    dynamodb.update_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
        UpdateExpression="SET venues = :empty",
        ExpressionAttributeValues={
            ':empty': {'M': {}}
        }
    )
    cached_suggestions.clear()
    last_suggestions_update_time = datetime.datetime.utcnow()


def add_suggestion(hex_uuid: str, venue: str, user_id: int, user_handle: str):
    cached_suggestions.append(Suggestion(hex_uuid, venue, user_id, user_handle))

    dynamodb.update_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
        UpdateExpression='SET venues.#uuid = :value',
        ConditionExpression='size(venues) < :max_suggestions',
        ExpressionAttributeNames={
            '#uuid': hex_uuid
        },
        ExpressionAttributeValues={
            ':value': {'M': {
                'name': {'S': venue},
                'user_id': {'N': str(user_id)},
                'user_handle': {'S': user_handle}
            }},
            ':max_suggestions': {'N': str(app.MAX_SUGGESTIONS)}
        }
    )


def remove_suggestion(hex_uuid: str):
    dynamodb.update_item(
        TableName=app.DYNAMO_WEEK_TABLE_NAME,
        Key={'id': {'S': 'current'}},
        UpdateExpression='REMOVE venues.#uuid',
        ExpressionAttributeNames={
            '#uuid': hex_uuid
        }
    )
    # Invalidate the cache
    global last_suggestions_update_time
    last_suggestions_update_time = datetime.datetime(day=1, month=1, year=1)


cached_membership: Dict[int, Tuple[str, datetime.datetime]] = {}


async def get_user_status_in_main_chat(bot: telegram.Bot, user_id: int) -> str:
    now = datetime.datetime.utcnow()

    cached_result = cached_membership.get(user_id)
    if cached_result is not None:
        status, last_lookup = cached_result
        if last_lookup + CACHE_TTL > now:
            # cached result is still valid.
            return status

    result = await bot.get_chat_member(
        chat_id=app.MAIN_CHAT_ID,
        user_id=user_id
    )

    print(f'User status of user id {user_id} is {result.status}')

    cached_membership[user_id] = (result.status, now)
    return result.status


async def is_user_part_of_main_chat(bot: telegram.Bot, user_id: int) -> bool:
    status = await get_user_status_in_main_chat(bot, user_id)
    return status in (telegram.ChatMember.OWNER, telegram.ChatMember.ADMINISTRATOR,
                      telegram.ChatMember.MEMBER, telegram.ChatMember.RESTRICTED)


async def is_user_admin_of_main_chat(bot: telegram.Bot, user_id: int) -> bool:
    status = await get_user_status_in_main_chat(bot, user_id)
    return status in (telegram.ChatMember.OWNER, telegram.ChatMember.ADMINISTRATOR)
