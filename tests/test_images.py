import unittest
from datetime import date
from bs4 import BeautifulSoup

from backend.sources.images import extract_event_image, discard_repeated_generic_images
from backend.sources.venues import Venue, make_event, parse_detail


class ArtworkTests(unittest.TestCase):
    def test_event_json_ld_prioritized_over_brand_image(self):
        html = """
        <meta property="og:image" content="https://club.example/assets/branding/club.jpg">
        <script type="application/ld+json">
          {"@context":"https://schema.org","@graph":[
            {"@type":"Organization","image":"https://club.example/organisation.jpg"},
            {"@type":"MusicEvent","image":{"url":"/posters/party-flyer.webp"}}]}
        </script>
        """
        art = extract_event_image(BeautifulSoup(html, "html.parser"),
                                  "https://club.example/events/party", "club")
        self.assertEqual(art, {
            "image_url": "https://club.example/posters/party-flyer.webp",
            "image_source": "club",
            "image_type": "event_flyer",
        })

    def test_detail_og_image(self):
        html = '<meta property="og:image" content="/uploads/2026/party.jpg">'
        art = extract_event_image(BeautifulSoup(html, "html.parser"),
                                  "https://club.example/events/party", "club")
        self.assertEqual(art["image_url"], "https://club.example/uploads/2026/party.jpg")
        self.assertEqual(art["image_type"], "event_image")

    def test_reject_logo_and_tracking_pixel(self):
        html = """<meta property="og:image" content="/images/logo.svg">
                  <meta name="twitter:image" content="/images/tracking-pixel.png">"""
        art = extract_event_image(BeautifulSoup(html, "html.parser"),
                                  "https://club.example/events/a", "club")
        self.assertIsNone(art["image_url"])

    def test_reject_http_and_data_url(self):
        html = """<meta property="og:image" content="http://club.example/art.jpg">
                  <meta name="twitter:image" content="data:image/png;base64,123">"""
        self.assertIsNone(extract_event_image(BeautifulSoup(html, "html.parser"),
                      "https://club.example/events/a", "club")["image_url"])

    def test_event_flyer_image_with_no_og_tag(self):
        html = '<article><img alt="Event Flyer" data-src="/art/poster-2026.webp"></article>'
        art = extract_event_image(BeautifulSoup(html, "html.parser"),
                                  "https://club.example/events/a", "club")
        self.assertEqual(art["image_url"], "https://club.example/art/poster-2026.webp")

    def test_generic_article_photo_not_used(self):
        html = '<article><img alt="Advertisement" src="https://ads.example/ad.jpg"></article>'
        self.assertIsNone(extract_event_image(BeautifulSoup(html, "html.parser"),
                           "https://club.example/events/a", "club")["image_url"])

    def test_venue_event_without_art_has_explicit_nulls(self):
        v = Venue("test", "Test", "https://club.example/", ("/event/",))
        e = make_event(v, "Party", date(2026, 10, 18), "23:00",
                       "https://club.example/event/party", date(2026, 10, 17))
        self.assertIsNone(e["image_url"])
        self.assertIsNone(e["image_source"])
        self.assertIsNone(e["image_type"])


    def test_repeated_brand_image_suppressed_without_harming_recurrent_flyer(self):
        bad = "https://club.example/site-share.jpg"
        good = "https://club.example/flyer-series.webp"
        events = [{"title": f"Unrelated act {n}", "image_url": bad,
                   "image_source": "club", "image_type": "event_image"} for n in range(5)]
        events += [{"title": "Weekly Residents", "image_url": good,
                    "image_source": "club", "image_type": "event_flyer"} for _ in range(5)]
        n, rejected = discard_repeated_generic_images(events)
        self.assertEqual(n, 5)
        self.assertIn(bad, rejected)
        self.assertTrue(all(e["image_url"] is None for e in events[:5]))
        self.assertTrue(all(e["image_url"] == good for e in events[5:]))

    def test_detail_parser_retains_image_fields(self):
        v = Venue("hive", "Hive", "https://www.hiveclub.ch/", ("/events/",))
        html = """<meta property="og:image" content="https://cdn.example/party.webp">
                  <h1>Party</h1><p>17. Oktober 2026</p><p>Start: 23:00</p>"""
        e = parse_detail(v, BeautifulSoup(html, "html.parser"),
                         "https://www.hiveclub.ch/events/party/", date(2026, 10, 17))
        self.assertEqual(e["image_url"], "https://cdn.example/party.webp")


if __name__ == "__main__":
    unittest.main()
