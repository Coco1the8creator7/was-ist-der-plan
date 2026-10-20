"""The quality snapshot measures fields, not source-recall percentages."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import backend.main as app


class CatalogMetricsTest(unittest.TestCase):
    def test_field_coverage_and_no_invented_manual_recall(self):
        d = datetime.now(app.TZ) + timedelta(days=1)
        day = d.date().isoformat()
        event = {
            "id": "exil-a", "source": "exil",
            "source_url": "https://example.org/events/test",
            "title": "Test Event", "date": day, "time": "20:00",
            "start_at": day + "T20:00:00+02:00",
            "venue": "Test Venue", "city": "Bern", "municipality": "Bern",
            "category": "Sound & Clöb", "description": "Documented detail",
            "price_chf": 10.0, "image_url": "https://example.org/flyer.jpg",
            "latitude": None, "longitude": None,
            "organizer": "Test association",
        }
        with tempfile.TemporaryDirectory() as root:
            events = Path(root) / "events.json"
            quality = Path(root) / "quality.json"
            with patch.object(app, "OUT", events), patch.object(app, "QUALITY", quality), \
                 patch.object(app, "RAW", Path(root) / "raw.json"), \
                 patch.object(app, "MATCHES", Path(root) / "matches.json"), \
                 patch.object(app, "ZURICH_SOURCES", ()), \
                 patch.object(app, "VENUES", ()), patch.object(app, "FAVORITES", ()), \
                 patch.object(app, "BERN_SOURCES", ()), patch.object(app, "MUNICIPAL_SOURCES", ()), \
                 patch.object(app, "crawl_exil", return_value=(1, [event], [], {})), \
                 patch.object(app, "crawl_koeniz", return_value=(0, [], ["fixture only"], {})):
                app.main()
            q = json.loads(quality.read_text())["sources"]["exil"]
            self.assertEqual(q["status"], "success")
            self.assertEqual(q["description_coverage"], 1)
            self.assertEqual(q["price_coverage"], 1)
            self.assertEqual(q["coordinate_coverage"], 0)
            self.assertEqual(q["municipality_coverage"], 1)
            self.assertEqual(q["organizer_coverage"], 1)
            self.assertEqual(q["sample_coverage"], None)
            self.assertEqual(json.loads(events.read_text())["total"], 1)


if __name__ == "__main__":
    unittest.main()

class RetentionTest(unittest.TestCase):
    def test_partial_and_failed_crawls_keep_prior_records(self):
        d=(datetime.now(app.TZ)+timedelta(days=1)).date().isoformat()
        old=dict(id='old',source='exil',source_url='https://example.org/events/old',title='Old concert',date=d,time='20:00',start_at=d+'T20:00:00+02:00',venue='Venue',category='Konzerte',description='Known description')
        for outcome in [(0,[],['temporary failure'],{}),(1,[],['unreadable occurrence'],{'pagination_complete':False})]:
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as root:
                out=Path(root)/'events.json';quality=Path(root)/'quality.json'
                out.write_text(json.dumps({'events':[old]}))
                with patch.object(app,'OUT',out),patch.object(app,'QUALITY',quality), \
                     patch.object(app,'RAW',Path(root)/'raw.json'),patch.object(app,'MATCHES',Path(root)/'matches.json'), \
                     patch.object(app,'VENUES',()),patch.object(app,'FAVORITES',()),patch.object(app,'BERN_SOURCES',()), \
                     patch.object(app,'MUNICIPAL_SOURCES',()),patch.object(app,'ZURICH_SOURCES',()), \
                     patch.object(app,'crawl_exil',return_value=outcome), \
                     patch.object(app,'crawl_koeniz',return_value=(0,[],['fixture'],{})):
                    app.main()
                self.assertEqual(json.loads(out.read_text())['events'][0]['description'],'Known description')
