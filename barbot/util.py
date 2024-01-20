from typing import List, Tuple

from barbot.database import Suggestion
from barbot.bars import Bars
from barbot import geo


def get_list_suggestions_message_text(suggestions: List[Suggestion]) -> str:
    return '\n'.join(f'{s.venue} (Suggested by @{s.user_handle})' for s in suggestions)


async def get_map_suggestions_message_data(bars: Bars, suggestions: List[Suggestion]) -> Tuple[bytes, str]:
    """Get the map photo and (MarkdownV2) text for some suggestions"""
    names = [s.venue for s in suggestions]
    unrecognised_names, barlist = bars.match_bars(names)
    letter_map, png = await geo.map_bars_to_png(barlist, (720, 720))
    if not png:
        return bytes(), ''
    markdown = ['_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}']
    table = {ord(m): ord(' ') for m in markdown}
    location_text = '\n'.join([f'*{letter}*: {bar.name}' for letter, bar in sorted(letter_map.items())] + [f'?: {n}' for n in unrecognised_names])
    # photo captions can only be 1024 characters long
    text = f'The currently suggested bars:\n{location_text}'.translate(table)[:1000]
    return png, text
