import tempfile
import unittest
from pathlib import Path

from ccf_awards.award_events import import_annotations
from ccf_awards.db import Database
from ccf_awards.source_listings import import_jeffhuang, list_source_listings, source_listing_detail


class SourceListingsTest(unittest.TestCase):
    def test_reviewed_title_variant_joins_existing_paper(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "awards.sqlite3")
            try:
                db.init()
                import_annotations(db.conn, {"format": "evidom-award-annotations-v1", "records": [{
                    "annotation_id": "page-0006-r001", "page_id": "page-0006", "year": 2007,
                    "official_award_name": "Best Paper", "title": "Dynamic 3D Scene Analysis from a Moving Vehicles",
                    "authors_raw": "B. Leibe", "paper_url": None,
                    "source_url": "https://example.org/cvpr-awards", "evidence": [], "note": None,
                }]})
                result = import_jeffhuang(db.conn, {"format": "jeffhuang-listings-v1",
                    "source_url": "https://jeffhuang.com/best_paper_awards/", "rows": [{
                        "source_row": 1685, "year": 2007, "venue": "CVPR", "area_raw": "Computer Vision",
                        "title": "Dynamic 3D Scene Analysis from a Moving Vehicle",
                        "authors_raw": "Bastian Leibe", "discovery_url": None,
                    }]})
                self.assertEqual(result["matched_event_papers"], 1)
                self.assertEqual(result["inserted_papers"], 0)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM award_papers").fetchone()[0], 1)
            finally:
                db.close()

    def test_fse_uses_software_engineering_context_not_cipher_conference(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "awards.sqlite3")
            try:
                db.init()
                import_jeffhuang(db.conn, {"format": "jeffhuang-listings-v1",
                    "source_url": "https://jeffhuang.com/best_paper_awards/", "rows": [{
                        "source_row": 1, "year": 2025, "venue": "FSE",
                        "area_raw": "Software Engineering", "title": "A Software Paper",
                        "authors_raw": "An Author", "discovery_url": None,
                    }]})
                row = list_source_listings(db.conn)["listings"][0]
                self.assertEqual(row["rank"], "A")
                cid = db.conn.execute("SELECT conference_id FROM source_listings").fetchone()[0]
                name = db.conn.execute("SELECT full_name FROM conferences WHERE id=?", (cid,)).fetchone()[0]
                self.assertIn("Foundations of Software Engineering", name)
            finally:
                db.close()

    def test_cross_source_dedup_preserves_award_and_source_meanings(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "awards.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")["id"]
                import_annotations(db.conn, {"format": "evidom-award-annotations-v1", "records": [{
                    "annotation_id": "page-0004-r001", "page_id": "page-0004", "year": 2026,
                    "official_award_name": "AAAI Outstanding Paper Awards",
                    "title": "Paper: Alpha", "authors_raw": "A. Author", "paper_url": None,
                    "source_url": "https://aaai.org/awards", "evidence": [], "note": None,
                }]})
                db.conn.execute("""INSERT INTO records
                    (id,conference_id,year,award_type,title,status,payload,sources,created_at,updated_at)
                    VALUES (?,?,?,?,?,'verified','{}','[]','2026','2026')""",
                    ("verified-beta", conf, 2026, "best_paper", "Paper Beta"))
                db.conn.commit()
                document = {"format": "jeffhuang-listings-v1",
                            "source_url": "https://jeffhuang.com/best_paper_awards/", "rows": [
                    {"source_row": 1, "year": 2026, "venue": "AAAI", "title": "Paper Alpha",
                     "area_raw": "AI", "authors_raw": "A. Author, Example University",
                     "discovery_url": "https://scholar.google.com/scholar?q=alpha"},
                    {"source_row": 2, "year": 2026, "venue": "AAAI", "title": "Paper Beta",
                     "area_raw": "AI", "authors_raw": "B. Author", "discovery_url": None},
                    {"source_row": 3, "year": 2026, "venue": "AAAI", "title": "Paper Gamma",
                     "area_raw": "AI", "authors_raw": "C. Author", "discovery_url": None},
                ]}
                first = import_jeffhuang(db.conn, document)
                self.assertEqual(first, {"rows": 3, "inserted_papers": 2,
                                         "matched_event_papers": 1, "matched_records": 1,
                                         "new_candidates": 1})
                second = import_jeffhuang(db.conn, document)
                self.assertEqual(second["inserted_papers"], 0)
                self.assertEqual(second["new_candidates"], 1)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM award_events").fetchone()[0], 1)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM source_listings").fetchone()[0], 3)
                event_match = list_source_listings(db.conn, relation="event")["listings"][0]
                detail = source_listing_detail(db.conn, event_match["id"])
                self.assertEqual(detail["events"][0]["official_award_name"], "AAAI Outstanding Paper Awards")
                self.assertIsNone(detail["paper_url"])
                self.assertIn("scholar.google.com", detail["discovery_url"])
                self.assertEqual(list_source_listings(db.conn, relation="record")["total"], 1)
                self.assertEqual(list_source_listings(db.conn, relation="new")["total"], 1)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM records").fetchone()[0], 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
