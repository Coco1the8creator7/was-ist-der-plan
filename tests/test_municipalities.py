"""Offline validation of two Swiss municipal calendars sharing one adapter."""
import unittest
from datetime import date
from bs4 import BeautifulSoup

from backend.categories import CULTURE, CONCERTS
from backend.sources.municipalities import (
    MUNICIPAL_SOURCES, event_links, parse_municipal_detail,
)

def html(name, body):
    return BeautifulSoup(f"<html><main><h1>{name}</h1>{body}</main></html>", "html.parser")

class TownEventTests(unittest.TestCase):
    def test_same_parser_handles_belp_public_festival(self):
        src = MUNICIPAL_SOURCES[0]
        doc = html("GTFV Lotto 2026",
          "<p>Datum/Zeit</p><p>31.10.2026 | 14:30 Uhr - 23:00 Uhr</p>"
          "<p>Beschreibung</p><p>Öffentlicher Vereinsanlass und Dorffest mit Verpflegung.</p>"
          "<p>Lokaliät</p><p>Gemeindezentrum</p>"
          "<p>Lokalität</p><p>Aaresaal</p>"
          "<p>Adresse</p><p>Belp</p>"
          "<p>Veranstalter</p><p>Gürbetaler Festverein</p><p>Termin in Kalender eintragen</p>")
        e, err = parse_municipal_detail(src, doc, "https://www.belp.ch/de/veranstaltungen/733_lotto", date(2026,10,20))
        self.assertIsNone(err)
        self.assertEqual(e["category"], CULTURE)
        self.assertEqual(e["city"], "Belp")
        self.assertEqual(e["venue"], "Aaresaal")
        self.assertEqual(e["time"], "14:30")
        self.assertEqual(e["organizer"], "Gürbetaler Festverein")

    def test_uttigen_compound_concert_explicit(self):
        src = MUNICIPAL_SOURCES[1]
        doc = html('Abendkonzert "Trio Lignum"',
           "<p>Datum/Zeit</p><p>01.11.2026 | 17:00 Uhr - 18:00 Uhr</p>"
           "<p>Kategorie</p><p>Diverses</p>"
           "<p>Lokalität</p><p>Kirchgemeindehaus Uttigen</p>"
           "<p>Strasse</p><p>Schulstutz 5</p>"
           "<p>Ort</p><p>Uttigen</p>"
           "<p>Veranstalter</p><p>Kirchgemeinde Kirchdorf</p>"
           "<p>Beschreibung</p><p>Klarinette Fagott und Klavier</p><p>Dokument</p>")
        e, err = parse_municipal_detail(src, doc,"https://www.uttigen.ch/de/veranstaltungen/303_trio", date(2026,10,20))
        self.assertIsNone(err)
        self.assertEqual(e["category"], CONCERTS)
        self.assertEqual(e["address"], "Schulstutz 5")
        self.assertEqual(e["municipality"], "Uttigen")

    def test_date_only_is_not_fabricated(self):
        src=MUNICIPAL_SOURCES[0]
        doc=html("Dorffest", "<p>Datum/Zeit</p><p>24.10.2026 | ganzer Tag</p><p>Ort</p><p>Belp</p>")
        e,err=parse_municipal_detail(src,doc,"https://www.belp.ch/de/veranstaltungen/1_dorffest",date(2026,10,20))
        self.assertIsNone(e)
        self.assertTrue(err.startswith("time_unknown"))

    def test_all_day_placeholder_is_not_real_start(self):
        src=MUNICIPAL_SOURCES[0]
        doc=html("Belper Samstagsmarkt", "<p>Datum/Zeit</p><p>24.10.2026 | 01:00 Uhr - 00:00 Uhr</p><p>Ort</p><p>Belp</p>")
        e,err=parse_municipal_detail(src,doc,"https://www.belp.ch/de/veranstaltungen/2_samstagsmarkt",date(2026,10,20))
        self.assertIsNone(e)
        self.assertTrue(err.startswith("time_unknown"))

    def test_missing_event_locality_is_not_assumed_from_website(self):
        src=MUNICIPAL_SOURCES[0]
        doc=html("Fest", "<p>Datum/Zeit</p><p>24.10.2026 | 18:00 Uhr</p><p>Veranstalter</p><p>Verein</p>")
        e,err=parse_municipal_detail(src,doc,"https://www.belp.ch/de/veranstaltungen/3_fest",date(2026,10,20))
        self.assertIsNone(e)
        self.assertIn("locality",err)

    def test_municipality_listing_links_are_host_restricted(self):
        src=MUNICIPAL_SOURCES[0]
        listing=BeautifulSoup(
          '<a href="/de/veranstaltungen/679_b%C3%A4uper-musig-nacht">Event</a>'
          '<a href="https://example.com/de/veranstaltungen/500_fake">Fake</a>'
          '<a href="/de/veranstaltungen/">Calendar home</a>', "html.parser")
        self.assertEqual(event_links(listing,src.index),
          ["https://www.belp.ch/de/veranstaltungen/679_b%C3%A4uper-musig-nacht"])

    def test_ostermundigen_concert_detail(self):
        src = next(v for v in MUNICIPAL_SOURCES if v.key == "gemeinde_ostermundigen")
        doc = html("Konzert Tell _ jazz à bientôt",
           "<p>Datum/Zeit</p><p>23.10.2026 | 20:00 Uhr - 23:30 Uhr</p>"
           "<p>Kategorie</p><p>Anlässe im Treffpunkt Mundige, Konzert, Musik</p>"
           "<p>Lokalität</p><p>Treffpunkt Mundige</p>"
           "<p>Strasse</p><p>Bernstrasse 101</p><p>Ort</p><p>Ostermundigen</p>"
           "<p>Veranstalter</p><p>Kulturverein Mundige</p>"
           "<p>Beschreibung</p><p>Jazzevent im Treffpunkt mit Musikern und zeitgenössischer Musik</p>"
           "<p>Termin in Kalender eintragen</p>")
        event, error = parse_municipal_detail(
            src, doc, "https://www.ostermundigen.ch/de/veranstaltungen/1122_konzert-tell",date(2026,10,20))
        self.assertIsNone(error)
        self.assertEqual(event["municipality"], "Ostermundigen")
        self.assertEqual(event["venue"], "Treffpunkt Mundige")
        self.assertEqual(event["category"], CONCERTS)
        self.assertEqual(event["time"], "20:00")

if __name__=="__main__":
    unittest.main()
