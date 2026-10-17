import unittest

from backend.categories import (
    SOUND, CULTURE, CONCERTS, CATEGORIES,
    classify_category, categorize_record,
)
from backend.sources.venues import Venue, make_event
from datetime import date


class ThreeCategoryTests(unittest.TestCase):
    def category(self, title, **kwargs):
        category = classify_category(title, **kwargs)
        self.assertIn(category, CATEGORIES)
        return category

    def test_exact_three_categories(self):
        self.assertEqual(CATEGORIES, ("Sound & Clöb", "Kultur & Workshops", "Konzerte"))

    def test_regular_dj_night(self):
        self.assertEqual(self.category("Shut Up And Dance", source="hive", venue="Hive Club"), SOUND)

    def test_supermarket_even_though_it_contains_market(self):
        self.assertEqual(self.category("MYSTIKA w/ Afrokillerz", source="supermarket",
                                       venue="Supermarket"), SOUND)

    def test_bar_music(self):
        self.assertEqual(self.category("Jazz Jam Session", source="stereo_bar",
                                       venue="Stereo Bar"), SOUND)

    def test_bar_literature_event(self):
        self.assertEqual(self.category("Literatur und Lesung", source="stereo_bar",
                                       venue="Stereo Bar"), CULTURE)

    def test_bar_community_discussion(self):
        self.assertEqual(self.category("Community-Diskussion: Kunst im Quartier",
                                       source="stereo_bar", venue="Stereo Bar"), CULTURE)

    def test_arts_at_club(self):
        self.assertEqual(self.category("Vernissage: Street Art", source="exil",
                                       venue="EXIL Club"), CULTURE)

    def test_kaufleuten_talk_and_literature(self):
        self.assertEqual(self.category("Caroline Wahl • Literatur", source="kaufleuten",
                                       venue="Kaufleuten"), CULTURE)
        self.assertEqual(self.category("Wissenschaft Talk am Abend", source="kaufleuten",
                                       venue="Kaufleuten"), CULTURE)

    def test_dynamo_course(self):
        self.assertEqual(self.category("SILBER RINGE SANDGUSS EINFÜHRUNG",
                                       source="dynamo", url="https://www.dynamo.ch/kurs/abc",
                                       venue="Dynamo"), CULTURE)

    def test_kaufleuten_party_title(self):
        self.assertEqual(self.category("LOCO HOUSE", source="kaufleuten",
                                       venue="Kaufleuten"), SOUND)

    def test_kaufleuten_late_night_unknown_title(self):
        self.assertEqual(self.category("HOTLINE", source="kaufleuten",
                                       venue="Kaufleuten", start_time="23:00"), SOUND)
        self.assertEqual(self.category("ADDICTION", source="kaufleuten",
                                       venue="Kaufleuten", start_time="23:00"), SOUND)

    def test_kaufleuten_late_cultural_event_stays_cultural(self):
        self.assertEqual(self.category("Autorenlesung", source="kaufleuten",
                                       venue="Kaufleuten", start_time="23:00"), CULTURE)

    def test_kaufleuten_party_from_actual_event_details(self):
        self.assertEqual(self.category("HOTLINE", source="kaufleuten", venue="Kaufleuten",
                        details="HOTLINE by Kobragypsy Samstag Türöffnung 23:00 "
                                "Veranstaltungsort: Jade Club. HOTLINE Party mit DJ."), SOUND)

    def test_club_designated_concert(self):
        self.assertEqual(self.category("Fink • Konzert", source="kaufleuten",
                                       venue="Kaufleuten", url="https://kaufleuten.ch/event/fink-konzert/"),
                         CONCERTS)
        self.assertEqual(self.category("tiny nest concert: Lev Tigrovich", source="kauz",
                                       venue="Kauz Klub"), CONCERTS)

    def test_dj_performance_never_concert(self):
        self.assertEqual(self.category("DJ Konzert Night", source="moods", venue="Moods"), SOUND)
        self.assertEqual(self.category("DJ SET • Concert", source="exil", venue="EXIL"), SOUND)

    def test_moods_dance_event_not_concert(self):
        self.assertEqual(self.category("Red Bull Dance Your Style", source="moods",
                                       venue="Moods"), CULTURE)

    def test_moods_concert_with_onstage_instruments(self):
        self.assertEqual(self.category("EKR", source="moods", venue="Moods",
                   details="EKR Album Release Line-Up EKR Gesang MC Wicht Keyboards Bass Schlagzeug Genre Rap"),
                   CONCERTS)

    def test_moods_dj_not_concert_from_generic_footer(self):
        self.assertNotEqual(self.category("DJ Enzout", source="moods", venue="Moods",
                    details="DJ Enzout Reggae Dancehall. Weitere Konzerte aus den Bereichen "
                            "Dieses Konzert findet stehend statt."), CONCERTS)

    def test_biography_concert_reference_not_enough(self):
        self.assertEqual(self.category("HOTLINE", source="kaufleuten", venue="Jade Club",
                    details="DJ Kobragypsy spielte bei Konzerten internationaler Künstler"), SOUND)

    def test_explicit_culture_format_before_nightlife(self):
        self.assertEqual(self.category("Gonzo Literatur Clubnacht", source="gonzo",
                                       venue="Gonzo Club"), CULTURE)

    def test_neutral_unrecognised_event(self):
        self.assertEqual(self.category("Einladung zur offenen Versammlung", source="dynamo",
                                       venue="Dynamo Zürich"), CULTURE)

    def test_make_event_uses_new_category(self):
        v = Venue("supermarket", "Supermarket", "https://www.supermarket.li/", ())
        event = make_event(v, "Outer Space", date(2026, 10, 18), "23:00",
                           "https://www.supermarket.li/programm", date(2026, 10, 17))
        self.assertEqual(event["category"], SOUND)

    def test_legacy_record_migration(self):
        self.assertEqual(categorize_record({
            "title":"Sven Regener • Literatur", "source":"kaufleuten",
            "venue":"Kaufleuten", "category":"Kultur & Unterhaltung"
        }), CULTURE)


if __name__ == "__main__":
    unittest.main()
