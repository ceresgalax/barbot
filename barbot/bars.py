import csv
import datetime
import re
import traceback
import unittest
import urllib.request
from typing import NamedTuple, List, Optional, Tuple, Sequence, Set

from . import app

CACHE_LIFETIME = datetime.timedelta(seconds=60)


class Bar(NamedTuple):
    name: str
    address: str
    latitude: float
    longitude: float
    plus_code: str
    aliases: Set[str]


def _normalize_name(name: str) -> str:
    return "".join(c.lower() for c in name if c.isalpha())


def _normalize_spreadsheet_url(url: str) -> str:
    """Make sure a URL points to the CSV version of a Google Sheet"""
    groups = re.search("docs.google.com/spreadsheets/d/([^/]+)", url)
    if not groups:
        return url  # not much we can do here :/
    identifier = groups.group(1)
    return f"https://docs.google.com/spreadsheets/d/{identifier}/export?format=csv"


def _fetch_bars(url: str) -> List[Bar]:
    with urllib.request.urlopen(url) as response:
        data = response.read().decode("utf-8")
    reader = csv.DictReader(data.splitlines())
    bars = []
    for row in reader:
        try:
            row["latitude"] = float(row["latitude"])
            row["longitude"] = float(row["longitude"])
            bars.append(
                Bar(
                    name=row["name"],
                    address=row["address"],
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    plus_code=row["plus_code"],
                    aliases=set(a for a in row["aliases"].split("|") if a),
                )
            )
        except Exception as err:
            print(f"Bad bar specification (`{err}`): `{row}`")
    return bars


class Bars:
    def __init__(self, bar_spreadsheet: str):
        self._bar_spreadsheet = _normalize_spreadsheet_url(bar_spreadsheet)
        self._cache: Optional[Tuple[datetime.datetime, List[Bar]]] = None

    def get_bars(self) -> List[Bar]:
        now = datetime.datetime.now()
        if self._cache and (now - self._cache[0]) < CACHE_LIFETIME:
            return self._cache[1]
        try:
            data = _fetch_bars(self._bar_spreadsheet)
        except Exception as err:
            print(f"Unable to update bar list: {err}")
            traceback.print_exc()
            # if we can't get new data, use old data even if it's expired
            if self._cache:
                return self._cache[1]
            # otherwise just say we have nothing I guess :<
            return []
        self._cache = (now, data)
        return data

    def match_bar(self, search: str) -> Optional[Bar]:
        search = _normalize_name(search)
        for bar in self.get_bars():
            if search == _normalize_name(bar.name):
                return bar
            if any(search == _normalize_name(a) for a in bar.aliases):
                return bar
        return None

    def match_bars(self, searches: Sequence[str]) -> Tuple[List[str], List[Bar]]:
        """Match fuzzy names to actual bars, also providing all fuzzy names that didn't match"""
        unknown = []
        known = []
        for search in searches:
            bar = self.match_bar(search)
            if bar:
                known.append(bar)
            else:
                unknown.append(search)
        return (unknown, known)


class TestBars(unittest.TestCase):
    def test_normalize_name(self):
        names = [
            "smuggler's cove",
            "Smuggler's Cove",
            "smugglers coVE",
            "smugglerscove",
        ]
        for name in names:
            self.assertEqual(_normalize_name(names[0]), _normalize_name(name))

    def test_normalize_spreadsheet_url(self):
        canonical = "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv"
        self.assertEqual(
            canonical,
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv"
            ),
        )
        self.assertEqual(
            canonical,
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export"
            ),
        )
        self.assertEqual(
            canonical,
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6"
            ),
        )
        self.assertEqual(
            canonical,
            _normalize_spreadsheet_url("docs.google.com/spreadsheets/d/1QBk_HhV6"),
        )
