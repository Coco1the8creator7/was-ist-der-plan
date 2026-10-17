import unittest
from datetime import date
from bs4 import BeautifulSoup
from backend.sources.venues import VENUES, known_date, known_time, parse_detail, supermarket_events


class SourceParsingTests(unittest.TestCase):
    def test_long_date(self):
        self.assertEqual(known_date("Samstag, 17. Oktober 2026"), date(2026, 10, 17))

    def test_numeric_date(self):
        self.assertEqual(known_date("17.10.2026"), date(2026, 10, 17))

    def test_unverified_year_not_guessed(self):
        self.assertIsNone(known_date("Samstag, 17. Oktober"))

    def test_time_label(self):
        self.assertEqual(known_time("Start: 23:30", "hive"), "23:30")

    def test_dont_guess_unlabelled_time(self):
        self.assertIsNone(known_time("Happy hour 18:00", "hive"))

    def test_ticket_time(self):
        self.assertEqual(known_time("Sa., 17. Oktober 2026, 18:00 Uhr", "kauz"), "18:00")

    def test_hive_real_page_time(self):
        self.assertEqual(known_time("Start: 17. October 2026 um 22:00", "hive"), "22:00")

    def test_dynamo_real_page_time(self):
        self.assertEqual(known_time("Sa. 17/10/2026 20:00–04:00", "dynamo"), "20:00")

    def test_dynamo_real_page_date(self):
        self.assertEqual(known_date("Sa. 17/10/2026 20:00–04:00"), date(2026, 10, 17))

    def test_detail(self):
        venue = next(v for v in VENUES if v.key == "hive")
        page = BeautifulSoup("<h1>Techno Nacht</h1><p>17. Oktober 2026</p><p>Start: 23:00</p>", "html.parser")
        event = parse_detail(venue, page, "https://www.hiveclub.ch/events/techno/", date(2026, 10, 17))
        self.assertEqual(event["title"], "Techno Nacht")
        self.assertEqual(event["time"], "23:00")

    def test_missing_time_rejected(self):
        venue = next(v for v in VENUES if v.key == "hive")
        page = BeautifulSoup("<h1>Event</h1><p>17. Oktober 2026</p>", "html.parser")
        self.assertIsNone(parse_detail(venue, page, "https://www.hiveclub.ch/events/abc/", date(2026, 10, 17)))

    def test_supermarket_programme(self):
        venue = next(v for v in VENUES if v.key == "supermarket")
        page = BeautifulSoup("<main><p>OKTOBER 2026</p><p>SA 17 23H SOME DJs</p></main>", "html.parser")
        found, events, errors, meta = supermarket_events(venue, page, date(2026, 10, 17))
        self.assertEqual((found, len(events), len(errors)), (1, 1, 0))
        self.assertEqual(events[0]["time"], "23:00")

    def test_supermarket_split_html_text(self):
        venue = next(v for v in VENUES if v.key == "supermarket")
        page = BeautifulSoup("<p>OKTOBER 2026</p><div>SA</div><div>17</div><div>23H</div><div>PARTY NAME: DJs</div>", "html.parser")
        found, events, errors, meta = supermarket_events(venue, page, date(2026, 10, 17))
        self.assertEqual((found, len(events), len(errors)), (1, 1, 0))
        self.assertEqual(events[0]["title"], "PARTY NAME")


if __name__ == "__main__":
    unittest.main()
