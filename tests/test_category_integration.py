"""Contract tests: published JSON and the category filter use the same labels."""
import json
import unittest
from pathlib import Path

from backend.categories import CATEGORIES, categorize_record

ROOT = Path(__file__).resolve().parents[1]


class CategoryIntegrationTests(unittest.TestCase):
    def test_published_catalog_has_only_new_categories(self):
        data = json.loads((ROOT / "site/data/events.json").read_text(encoding="utf-8"))
        self.assertTrue(data["events"])
        actual = {item["category"] for item in data["events"]}
        self.assertEqual(actual, set(CATEGORIES))

    def test_published_ids_and_source_links_preserved(self):
        data = json.loads((ROOT / "site/data/events.json").read_text(encoding="utf-8"))
        for item in data["events"]:
            self.assertTrue(item["id"])
            self.assertTrue(item["source_url"].startswith("https://"))

    def test_frontend_filter_has_exact_categories(self):
        page = (ROOT / "site/index.html").read_text(encoding="utf-8")
        self.assertIn("const PUBLIC_CATEGORIES=['Sound & Clöb','Kultur & Workshops','Konzerte'];", page)
        self.assertIn("category:frontendCategory(raw)", page)
        self.assertIn("for(const category of PUBLIC_CATEGORIES){", page)

    def test_migrated_records_are_stable_without_detail_info(self):
        data = json.loads((ROOT / "site/data/events.json").read_text(encoding="utf-8"))
        # Only explicit concert labels need to match without event-page context.
        for item in data["events"]:
            if " • Konzert" in item["title"] and "Comedy" not in item["title"]:
                self.assertEqual(categorize_record(item), "Konzerte")


if __name__ == "__main__":
    unittest.main()
