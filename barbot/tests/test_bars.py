import unittest

from barbot.bars import _normalize_name, _normalize_spreadsheet_url, _parse_bars


class TestBars(unittest.TestCase):
    def test_normalize_name_with_numbers(self):
        self.assertEqual("440", _normalize_name("440"))
        self.assertEqual("440castro", _normalize_name("440 Castro"))

    def test_normalize_name_with_casing(self):
        self.assertEqual("smugglerscove", _normalize_name("Smugglers COVE"))
        self.assertEqual("smugglerscove", _normalize_name("Smugglers Cove"))
        self.assertEqual("smugglerscove", _normalize_name("smugglers coVE"))

    def test_normalize_name_with_nonalphanumeric(self):
        self.assertEqual("smugglerscove", _normalize_name("smuggler's cove"))
        self.assertEqual("smugglerscove", _normalize_name("'smuggler's cove\""))

    def test_normalize_name_with_spacing(self):
        self.assertEqual("smugglerscove", _normalize_name(" smugglers\tCove"))
        self.assertEqual("smugglerscove", _normalize_name("smugglers \n cove "))
        self.assertEqual("smugglerscove", _normalize_name(" sm u gglersc ove"))

    def test_normalize_name_with_substitutions(self):
        self.assertNotEqual("smugglerscove", _normalize_name("Śmugglers cove"))
        self.assertNotEqual("smugglerscove", _normalize_name("smugglers c0ve"))

    def test_normalize_spreadsheet_url_full(self):
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv"
            ),
        )

    def test_normalize_spreadsheet_url_noformat(self):
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export"
            ),
        )
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export/"
            ),
        )

    def test_normalize_spreadsheet_url_querystring(self):
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?level=four"
            ),
        )

    def test_normalize_spreadsheet_url_noexport(self):
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6"
            ),
        )
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url(
                "https://docs.google.com/spreadsheets/d/1QBk_HhV6/"
            ),
        )

    def test_normalize_spreadsheet_url_noscheme(self):
        self.assertEqual(
            "https://docs.google.com/spreadsheets/d/1QBk_HhV6/export?format=csv",
            _normalize_spreadsheet_url("https://docs.google.com/spreadsheets/d/1QBk_HhV6"),
        )

    def test_parse_bars(self):
        data = '''name,address,latitude,longitude,plus_code,aliases
Blackbird,"2124 Market St, San Francisco, CA 94114",37.76725382,-122.429588,"QH8C+W5 Duboce Triangle, San Francisco, CA",
Churchill Cocktail Bar,"198 Church St, San Francisco, CA 94114",37.7678905,-122.4291782,"QH9C+58 Duboce Triangle, San Francisco, CA",churchill
Finnegans Wake,"937 Cole St, San Francisco, CA 94117",37.76529613,-122.4501335,"QG8X+4W Cole Valley, San Francisco, CA",finnegans
Hobson's Choice,"1601 Haight St, San Francisco, CA 94117",37.76968435,-122.4487544,"QH92+VG Haight-Ashbury, San Francisco, CA",hobsons
Last Rites,"718 14th St, San Francisco, CA 94114",37.7678973,-122.4294669,"QH9C+56 Duboce Triangle, San Francisco, CA",last rights
Local Edition,"691 Market St, San Francisco, CA 94105",37.78764413,-122.4031763,"QHQW+2P Yerba Buena, San Francisco, CA",
Noc Noc,"557 Haight St, San Francisco, CA 94117",37.7718871,-122.4314015,"QHC9+PC Lower Haight, San Francisco, CA",nock nock|knock knock
Pagan Idol,"375 Bush St, San Francisco, CA 94104",37.79072444,-122.4036048,"QHRW+7J Union Square, San Francisco, CA",pagan idle|pagin idol|pagin idle
Pilsner Inn,"225 Church St, San Francisco, CA 94114",37.76711585,-122.4287876,"QH8C+RF Mission Dolores, San Francisco, CA",pilsner
SF Eagle,"398 12th St, San Francisco, CA 94103",37.76999463,-122.4134,"QH9P+XJ SoMa, San Francisco, CA",eagle|the eagle|eagle sf|sf eagle|the sf eagle|the eagle sf
Smuggler's Cove,"650 Gough St, San Francisco, CA 94102",37.7794161,-122.4233717,"QHHG+QM Fillmore District, San Francisco, CA",smugglers|smuggler
Standard Deviant Brewing,"280 14th St, San Francisco, CA 94103",37.76840917,-122.4194822,"QH9J+96 Mission District, San Francisco, CA",standard deviant
The Irish Bank,"10 Mark Ln, San Francisco, CA 94108",37.79039514,-122.4045096,"QHRW+56 Union Square, San Francisco, CA",irish bank
The Zombie Village,"441 Jones St, San Francisco, CA 94102",37.78551504,-122.4132064,"QHPP+6P Tenderloin, San Francisco, CA",zombie village
Trick Dog,"3010 20th St, San Francisco, CA 94110",37.75921458,-122.4111932,"QH5Q+MG Mission District, San Francisco, CA",
Upcider,"1160 Polk St 2nd floor, San Francisco, CA 94109",37.78753092,-122.4198176,"QHQJ+23 Lower Nob Hill, San Francisco, CA",
Zeitgeist,"199 Valencia St, San Francisco, CA 94103",37.77002787,-122.4221187,"QHCH+25 SoMa, San Francisco, CA",'''
        bars = _parse_bars(data)
        self.assertEqual(17, len(bars))
