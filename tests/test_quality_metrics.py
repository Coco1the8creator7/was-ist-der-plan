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
                 patch.object(app, "VENUES", ()), patch.object(app, "FAVORITES", ()), \
                 patch.object(app, "BERN_SOURCES", ()), patch.object(app, "MUNICIPAL_SOURCES", ()), \
                 patch.object(app, "crawl_exil", return_value=(1, [event], [], {})):
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
