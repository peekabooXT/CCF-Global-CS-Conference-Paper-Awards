import json
import tempfile
import unittest
from pathlib import Path

from ccf_awards.award_events import event_detail, import_annotations, list_events, venue_for
from ccf_awards.db import Database
from ccf_awards.ontology import classify_award


class AwardEventsTest(unittest.TestCase):
    def test_category_precedence_and_lossless_name(self):
        self.assertEqual(classify_award("BEST PAPER HONORABLE MENTION")["category"], "honorable_mention")
        self.assertEqual(classify_award("BEST PAPER RUNNER-UP")["category"], "runner_up")
        self.assertEqual(classify_award("SIGCOMM Test of Time")["category"], "test_of_time")
        self.assertTrue(classify_award("Best Student Paper")["student_only"])

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
                listing = list_events(db.conn, venue="OSDI", category="best")
                self.assertEqual(listing["total"], 1)
                event = event_detail(db.conn, listing["events"][0]["id"])
                self.assertEqual(len(event["papers"]), 2)
                self.assertEqual(event["status"], "pending")
                self.assertEqual(event["official_award_name"], "USENIX Best Paper / OSDI '25")
                self.assertEqual(event["rank"], "A")
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM records").fetchone()[0], 0)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
