import json
import tempfile
import unittest
from pathlib import Path

from global_cs_paper_awards_agent.award_events import event_detail, import_annotations, list_events, reclassify_events, venue_for
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.ontology import CATEGORIES, classify_award


class AwardEventsTest(unittest.TestCase):
    def test_archived_categories_are_readable_without_database_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                originals = [
                    ("Best Paper Award", "best", "paper"),
                    ("Outstanding Paper Award", "outstanding", "paper"),
                    ("Distinguished Paper Award", "distinguished", "paper"),
                    ("Best Poster Award", "best", "other"),
                    ("Best Student Paper Award", "best_student", "student"),
                ]
                for i, (name, legacy, expected) in enumerate(originals):
                    import_annotations(db.conn, {"format": "evidom-award-annotations-v1",
                        "review_status": "verified", "records": [{
                            "annotation_id": f"page-0004-r{i}", "page_id": "page-0004", "year": 2026,
                            "official_award_name": name, "title": f"Paper {i}",
                            "source_url": "https://aaai.org/awards", "evidence": [],
                        }]})
                    db.conn.execute("UPDATE award_events SET category=? WHERE official_award_name=?", (legacy, name))
                db.conn.commit()
                before = [tuple(r) for r in db.conn.execute("SELECT * FROM award_events ORDER BY id")]
                self.assertEqual(list_events(db.conn)["total"], 5)
                for name, legacy, expected in originals:
                    result = list_events(db.conn, venue="AAAI", category=expected, query=name)
                    self.assertEqual(result["total"], 1)
                    event = event_detail(db.conn, result["events"][0]["id"])
                    self.assertEqual(event["category"], expected)
                    self.assertEqual(event["official_award_name"], name)
                    self.assertEqual(event["status"], "verified")
                paged = list_events(db.conn, category="paper", limit=1, offset=2)
                self.assertEqual(paged["total"], 3)
                self.assertEqual(len(paged["events"]), 1)
                self.assertEqual(before, [tuple(r) for r in db.conn.execute("SELECT * FROM award_events ORDER BY id")])
            finally:
                db.close()

    def test_category_precedence_and_lossless_name(self):
        self.assertEqual(classify_award("BEST PAPER HONORABLE MENTION")["category"], "other")
        self.assertEqual(classify_award("BEST PAPER RUNNER-UP")["category"], "other")
        self.assertEqual(classify_award("Best Paper Awards Runners-Up")["category"], "other")
        self.assertEqual(classify_award("BEST STUDENT PAPER RUNNER-UP")["category"], "other")
        self.assertEqual(classify_award("Test of Time Honorable Mention")["category"], "other")
        self.assertEqual(classify_award("SIGCOMM Test-of-time award (2026)")["category"], "other")
        self.assertEqual(classify_award("Best Paper Awards")["category"], "paper")
        self.assertEqual(classify_award("Outstanding Paper Awards")["category"], "paper")
        self.assertEqual(classify_award("AAAI Distinguished Papers")["category"], "paper")
        self.assertEqual(classify_award("Best Student Paper Award")["category"], "student")
        self.assertEqual(classify_award("Best Demonstration Award")["category"], "other")
        self.assertEqual(classify_award("AAAI-26 Best Demonstration Awards / Runner Up")["category"], "other")
        self.assertEqual(classify_award("AAAI-26 Best Poster Award")["category"], "other")
        self.assertEqual(classify_award("Best Short Paper Award")["category"], "other")
        self.assertEqual(classify_award("Best 10-year Old Paper")["category"], "other")
        self.assertEqual(classify_award(None)["category"], "other")
        self.assertTrue(classify_award("Best Student Paper")["student_only"])
        self.assertEqual(set(CATEGORIES), {"paper", "student", "other"})
        self.assertNotIn("2026", " ".join(CATEGORIES.values()))

    def test_reclassification_preserves_original_name_and_review(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                import_annotations(db.conn, {"format": "evidom-award-annotations-v1",
                    "review_status": "verified", "records": [{
                        "annotation_id": "page-0004-r999", "page_id": "page-0004", "year": 2026,
                        "official_award_name": "2026 Outstanding Paper Awards",
                        "title": "A Paper", "authors_raw": "A. Author", "paper_url": None,
                        "source_url": "https://aaai.org/awards", "evidence": [], "note": None,
                    }]})
                db.conn.execute("UPDATE award_events SET category='outstanding'")
                db.conn.commit()
                self.assertEqual(reclassify_events(db.conn), 1)
                self.assertEqual(reclassify_events(db.conn), 0)
                event = db.conn.execute(
                    "SELECT official_award_name,category,status FROM award_events").fetchone()
                self.assertEqual(tuple(event), ("2026 Outstanding Paper Awards", "paper", "verified"))
            finally:
                db.close()

    def test_reclassification_removes_old_best_label_from_poster(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                import_annotations(db.conn, {"format": "evidom-award-annotations-v1",
                    "review_status": "verified", "records": [{
                        "annotation_id": "page-0004-r998", "page_id": "page-0004", "year": 2026,
                        "official_award_name": "AAAI-26 Best Poster Award",
                        "title": "A Poster", "authors_raw": "A. Author", "paper_url": None,
                        "source_url": "https://aaai.org/awards", "evidence": [], "note": None,
                    }]})
                db.conn.execute("UPDATE award_events SET category='paper'")
                db.conn.commit()
                self.assertEqual(reclassify_events(db.conn), 1)
                event = db.conn.execute(
                    "SELECT official_award_name,category,status FROM award_events").fetchone()
                self.assertEqual(tuple(event), ("AAAI-26 Best Poster Award", "other", "verified"))
            finally:
                db.close()

    def test_mixed_usenix_source_uses_record_label(self):
        self.assertEqual(venue_for("page-0005", "USENIX Best Paper / OSDI '25"), "OSDI")
        self.assertEqual(venue_for("page-0005", "USENIX Best Paper / NSDI '25"), "NSDI")

    def test_event_can_have_multiple_papers_and_import_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                rows = []
                for i in range(2):
                    rows.append({"annotation_id": f"page-0005-r00{i+1}", "page_id": "page-0005",
                                 "year": 2025, "official_award_name": "USENIX Best Paper / OSDI '25",
                                 "title": f"Paper {i+1}", "authors_raw": "Author", "paper_url": None,
                                 "source_url": "https://www.usenix.org/conferences/best-papers",
                                 "evidence": [{"quote": "Best Paper"}], "note": "待复核"})
                doc = {"format": "evidom-award-annotations-v1", "records": rows}
                for _ in range(2):
                    counts = import_annotations(db.conn, doc)
                    self.assertEqual(counts["annotations"], 2)
                listing = list_events(db.conn, venue="OSDI", category="paper")
                self.assertEqual(listing["total"], 1)
                event = event_detail(db.conn, listing["events"][0]["id"])
                self.assertEqual(len(event["papers"]), 2)
                self.assertEqual(event["status"], "pending")
                self.assertEqual(event["official_award_name"], "USENIX Best Paper / OSDI '25")
                self.assertEqual(event["rank"], "A")
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM records").fetchone()[0], 0)
                verified_doc = {**doc, "review_status": "verified"}
                import_annotations(db.conn, verified_doc)
                self.assertEqual(event_detail(db.conn, event["id"])["status"], "verified")
                self.assertEqual(db.conn.execute(
                    "SELECT COUNT(*) FROM award_event_papers WHERE status='verified'"
                ).fetchone()[0], 2)
                import_annotations(db.conn, doc)
                self.assertEqual(event_detail(db.conn, event["id"])["status"], "verified")
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
