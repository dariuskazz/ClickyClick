import unittest

from i18n import CATALOGS, LANGUAGES, translate


class I18nTests(unittest.TestCase):
    def test_requested_languages(self):
        self.assertEqual(set(LANGUAGES), {"EN", "LT", "PL", "UA", "RU", "NO", "FR", "DE", "IT", "ES"})

    def test_catalogs_are_complete(self):
        expected = set(CATALOGS["EN"])
        for catalog in CATALOGS.values():
            self.assertEqual(set(catalog), expected)
            self.assertTrue(all(value.strip() for value in catalog.values()))

    def test_unknown_language_falls_back(self):
        self.assertEqual(translate("unknown", "stop_all"), "Stop All")


if __name__ == "__main__":
    unittest.main()
