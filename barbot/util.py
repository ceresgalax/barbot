from typing import List, Tuple

from barbot.app import AppSettings
from barbot.database import Suggestion
from barbot.bars import Bars
from barbot import geo


def get_list_suggestions_message_text(suggestions: List[Suggestion]) -> str:
    return '\n'.join(f'{s.venue} (Suggested by @{s.user_handle})' for s in suggestions)


async def get_map_suggestions_message_data(bars: Bars, suggestions: List[Suggestion], app: AppSettings) -> Tuple[bytes, str]:
    """Get the map photo and (MarkdownV2) text for some suggestions"""
    names = [s.venue for s in suggestions]
    unrecognised_names, barlist = bars.match_bars(names)
    letter_map, png = await geo.map_bars_to_png(barlist, (720, 720), app)
    if not png:
        return bytes(), ''
    location_text = '\n'.join([f'*{letter}*: {escape_markdown_v2(bar.name)}' for letter, bar in sorted(letter_map.items())] + [f'?: {escape_markdown_v2(n)}' for n in unrecognised_names])
    # photo captions can only be 1024 characters long
    # TODO: How do we make sure we don't strip out markdown characters? Will telegram fail us for omitting closing markdown?
    text = f'The currently suggested bars:\n{location_text}'[:1000]
    # In case we chop an escaped character, strip off any trailing backslashes
    text.rstrip('\\')
    return png, text


def escape_markdown_v2(text: str) -> str:
    markdown = {'_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'}
    return ''.join('\\' + c if c in markdown else c for c in text)
