"""Offline fixtures for the five Bern programme shapes, including distinct occurrences."""
import unittest
from datetime import date
from bs4 import BeautifulSoup

from backend.categories import CULTURE, CONCERTS, SOUND
from backend.sources.bern import (
    BERN_SOURCES, DAMPF_OCCURRENCE, DACH_URL, short_date,
    bierhuebeli, dampfzentrale, dachstock, gaskessel, isc,
)

TODAY = date(2026, 10, 20)
def src(mode):
    return next(s for s in BERN_SOURCES if s.mode == mode)
def soup(html):
    return BeautifulSoup(html, "html.parser")

class FakeClient:
    def __init__(self, pages):
        self.pages = {u: soup(h) for u, h in pages.items()}
        self.read = []
    def fetch(self, u):
        self.read.append(u)
        return soup(str(self.pages[u]))

class BernProgrammeTests(unittest.TestCase):
    def test_dachstock_dated_link_and_doors(self):
        s = src("dachstock")
        u = "https://www.dachstock.ch/events/23-10-2026-test-konzert"
        index = soup(f'<a href="{u}">Freitag</a>')
        client = FakeClient({u: "<main><p>Konzert</p><h1>Test Konzert</h1><p>Doors: 20:00 Ort: Dachstock</p><p>Eine Konzertveranstaltung mit echten Bands in Bern und einem umfangreichen Musikprogramm.</p></main>"})
        found, events, errors, _ = dachstock(s, client, index, TODAY)
        self.assertEqual((found, len(events), errors), (1, 1, []))
        self.assertEqual(events[0]["category"], CONCERTS)
        self.assertEqual(events[0]["municipality"], "Bern")
        self.assertEqual(events[0]["time"], "20:00")

    def test_gaskessel_includes_workshop_without_making_it_party(self):
        s = src("gaskessel")
        html = "<main><p>Sa 24.10.26</p><h2>DJ Workshop</h2><p>Workshop</p><p>Doors</p><p>09:00</p><p>Fr 30.10.26</p><h2>Some DJ Party</h2><p>Party</p><p>Doors</p><p>23:00</p></main>"
        found, ev, errors, _ = gaskessel(s, None, soup(html), TODAY)
        self.assertEqual((found, len(ev), errors), (2, 2, []))
        self.assertEqual([x["category"] for x in ev], [CULTURE, SOUND])
        self.assertNotEqual(ev[0]["id"], ev[1]["id"])

    def test_bierhuebeli_uses_start_not_doors(self):
        s = src("bierhuebeli")
        u = "https://bierhuebeli.ch/event/test-band/"
        client = FakeClient({
            "https://bierhuebeli.ch/konzerte/": f'<a href="{u}">Test Band</a>',
            "https://bierhuebeli.ch/partys/": "<p>Keine Partys</p>",
            u: "<main><p>Dienstag, 20.10.2026</p><h1>Test Band</h1><p>Türöffnung:16:00 Beginn: 19:30</p><p>Hier spielen Musiker auf der Bühne und präsentieren ihr neues Programm mit abwechslungsreichen Liedern.</p></main>",
        })
        found, ev, errors, _ = bierhuebeli(s, client, soup(""), TODAY)
        self.assertEqual((found, len(ev), errors), (1, 1, []))
        self.assertEqual(ev[0]["category"], CONCERTS)
        self.assertEqual(ev[0]["time"], "19:30")

    def test_isc_listing_format_and_calendar_timestamp(self):
        s = src("isc")
        u = "https://isc-club.ch/programm/test-band/"
        index = soup(f'<a href="{u}">14.11. Sa Sa 14.11. Konzert - Indie, Rock Test Band</a>')
        client = FakeClient({u: '<main><h1>Test Band</h1><p>Türöffnung 19:30 Uhr</p><p>Add to Calendar 2026-11-14 19:30:00 2026-11-15 23:00:00 Europe/Zurich</p><p>Ein ausführlicher Text über das Konzert, die Musiker und den Abend im ISC Club Bern.</p></main>'})
        found, ev, errors, _ = isc(s, client, index, TODAY)
        self.assertEqual((found, len(ev), errors), (1, 1, []))
        self.assertEqual(ev[0]["category"], CONCERTS)

    def test_dampfzentrale_separate_performances_same_detail_url(self):
        s = src("dampfzentrale")
        u = "https://www.dampfzentrale.ch/event/tanz-projekt/"
        index = soup(f'<main><a href="{u}">Tanz Projekt DI 20.10.26 20:00</a><a href="{u}">Tanz Projekt MI 21.10.26 20:00</a></main>')
        client = FakeClient({u: "<main><h1>Tanz Projekt</h1><p>Ein künstlerischer Tanzabend mit verschiedenen Ausdrucksformen und Gesprächen nach der Aufführung.</p></main>"})
        found, ev, errors, _ = dampfzentrale(s, client, index, TODAY)
        self.assertEqual((found, len(ev), errors), (2, 2, []))
        self.assertNotEqual(ev[0]["id"], ev[1]["id"])
        self.assertEqual(len(client.read), 1)
        self.assertTrue(all(x["category"] == CULTURE for x in ev))

    def test_invalid_and_missing_dates_are_not_invented(self):
        self.assertIsNone(short_date(DAMPF_OCCURRENCE.search("MI 31.02.26 20:00")))
        s = src("dampfzentrale")
        found, ev, _, _ = dampfzentrale(s, FakeClient({}), soup('<a href="/event/abc/">Workshop ohne Uhrzeit</a>'), TODAY)
        self.assertEqual((found, len(ev)), (0, 0))

if __name__ == "__main__":
    unittest.main()
