import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.award_events import import_annotations
from ccf_awards.db import Database
from ccf_awards.paper_search import award_names, search_papers
from ccf_awards.source_listings import import_jeffhuang
from ccf_awards.ontology import CATEGORIES
from ccf_awards.web_helpers import csv_bytes, import_demo


class PaperSearchTest(unittest.TestCase):
    def test_original_award_names_and_event_papers_are_searchable(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                import_demo(db)
                import_annotations(db.conn, {
                    "format": "evidom-award-annotations-v1", "review_status": "verified",
                    "records": [{
                        "annotation_id": "page-0004-r001", "page_id": "page-0004",
                        "year": 2026, "official_award_name": "AAAI Outstanding Paper Awards",
                        "title": "An Awarded Paper", "authors_raw": "Jane Scholar",
                        "paper_url": None, "source_url": "https://aaai.org/awards",
                        "evidence": [{"quote": "An Awarded Paper"}], "note": None,
                    }],
                })
                names = award_names(db.conn)
                self.assertIn("AAAI Outstanding Paper Awards", names)
                self.assertIn("Best Paper Awards", names)
                rows = search_papers(db, {"award_name": "AAAI Outstanding Paper Awards", "status": "verified"})
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["title"], "An Awarded Paper")
                self.assertEqual(rows[0]["award_name"], "AAAI Outstanding Paper Awards")
                self.assertEqual(rows[0]["category"], "paper")
                self.assertEqual(len(search_papers(db, {"category": "paper", "status": "verified"})), 1)
                self.assertIn("AAAI Outstanding Paper Awards", csv_bytes(rows).decode("utf-8-sig"))
                self.assertEqual(search_papers(db, {"author": "nobody", "status": "verified"}), [])
                self.assertEqual(search_papers(db, {"award_name": "AAAI Outstanding Paper Awards",
                                                    "affiliation": "unknown", "status": "verified"}), [])
            finally:
                db.close()

    def test_unlinked_verified_listing_uses_broad_source_category_without_fabricated_name(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                import_jeffhuang(db.conn, {"format": "jeffhuang-listings-v1",
                    "review_status": "verified", "source_url": "https://jeffhuang.com/best_paper_awards/",
                    "rows": [{"source_row": 1, "year": 2025, "venue": "FSE",
                              "area_raw": "Software Engineering", "title": "A New Paper",
                              "authors_raw": "An Author", "discovery_url": None}]})
                rows = search_papers(db, {"category": "paper", "status": "verified"})
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["source_kind"], "source_listing")
                self.assertIsNone(rows[0]["award_name"])
                self.assertIn(rows[0]["category"], CATEGORIES)
                csv = csv_bytes(rows).decode("utf-8-sig")
                self.assertIn("最佳／杰出论文奖", csv)
                self.assertIn("来源未提供原名", csv)
                self.assertIn("聚合收录来源", csv)
                self.assertNotIn("获奖来源,https://jeffhuang", csv)
                self.assertEqual(search_papers(db, {"category": "student", "status": "verified"}), [])
            finally:
                db.close()

    def test_auto_search_reuses_exact_llm_connection(self):
        try:
            from api import CollectReq, LLMConfig, _do_collect
        except ImportError as exc:
            self.skipTest(f"API test dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")
                req = CollectReq(conference_id=conf["id"], year=2026, strategy="auto",
                                 llm=LLMConfig(provider="custom", api_key="same-key",
                                               base_url="https://example.org/v1", model="same-model"))
                with patch("api.ResponsesWebSearch") as search, patch("api.auto_collect_one", return_value={}) as collect:
                    _do_collect(db, req, lambda _: None)
                search.assert_called_once_with(api_key="same-key", base_url="https://example.org/v1",
                                               model="same-model")
                self.assertEqual(collect.call_args.kwargs["llm"].key, "same-key")
                unsupported = CollectReq(conference_id=conf["id"], year=2026, strategy="auto",
                                         llm=LLMConfig(provider="deepseek", api_key="key"))
                with self.assertRaisesRegex(ValueError, "web_search"):
                    _do_collect(db, unsupported, lambda _: None)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
