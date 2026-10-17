import unittest
from datetime import date
from bs4 import BeautifulSoup
from backend.sources.favourites import (
    FAVORITES, event_yearless, parse_gonzo, parse_stereo, parse_ubwg_detail
)


class FavouriteSourceTests(unittest.TestCase):
    def test_yearless_december_to_january(self):
        self.assertEqual(event_yearless(2, 1, date(2026, 12, 25)), date(2027, 1, 2))

    def test_stereo_official_programme(self):
        doc = BeautifulSoup("""
            <h1>[PROGRAMM]</h1>
            <p>jeweils donnerstags, freitags und samstags ab 22:00 Uhr.</p>
            <p>17.10. Kejeblos</p><p>22.10. DJ Skiworld</p><h2>[MENU]</h2>
            <p>Donnerstag 19:00 bis 02:00 Uhr</p>
        """, "html.parser")
        found, events, errors, details = parse_stereo(doc, date(2026, 10, 17))
        self.assertEqual(found, 2)
        self.assertEqual(errors, [])
        self.assertEqual([(e["title"], e["time"]) for e in events],
                         [("Kejeblos", "22:00"), ("DJ Skiworld", "22:00")])

    def test_frieda_event_detail(self):
        html = """<h1>House Of Frieda</h1><h2>Samstag, 17. Oktober · ab 23:00</h2>
                  <h2>Line-Up</h2><p>Aline</p>"""
        url = "https://ubwg.ch/event/house-of-frieda-friedas-buexe-zuerich-17-10-2026/"
        event, error = parse_ubwg_detail(BeautifulSoup(html, "html.parser"), url, date(2026, 10, 17))
        self.assertIsNone(error)
        self.assertEqual((event["title"], event["time"], event["date"]),
                         ("House Of Frieda", "23:00", "2026-10-17"))

    def test_frieda_rejects_mismatched_date(self):
        url = "https://ubwg.ch/event/house-of-frieda-friedas-buexe-zuerich-17-10-2026/"
        doc = BeautifulSoup("<h1>House Of Frieda</h1><h2>Samstag, 18. Oktober · ab 23:00</h2>", "html.parser")
        event, error = parse_ubwg_detail(doc, url, date(2026, 10, 17))
        self.assertIsNone(event)
        self.assertIn("disagree", error)

    def test_gonzo_requires_explicit_title_and_time(self):
        html = """<main><p>SAMSTAG 17. OKTOBER 23H</p><p>Mindestalter 20+</p>
                  <h2>BARKADA BASS</h2></main>"""
        found, events, errors, stats = parse_gonzo(BeautifulSoup(html, "html.parser"),
                                                    date(2026, 10, 17))
        self.assertEqual(found, 1)
        self.assertEqual(events[0]["title"], "BARKADA BASS")
        self.assertEqual(events[0]["time"], "23:00")


if __name__ == "__main__":
    unittest.main()
