import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.db import Database


class CoverageReportTest(unittest.TestCase):
    def test_existing_coverage_table_is_migrated_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.sqlite3"
            conn = sqlite3.connect(path)
            conn.execute("""CREATE TABLE coverage (
                conference_id TEXT, year INTEGER, award_type TEXT, state TEXT,
                evidence_url TEXT, note TEXT, updated_at TEXT,
                PRIMARY KEY(conference_id,year,award_type))""")
            conn.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                         ("legacy", 2024, "best_paper", "checked", "https://example.org", "kept", "2024-01-01"))
            conn.execute("INSERT INTO coverage VALUES (?,?,?,?,?,?,?)",
                         ("legacy", 2024, "best_student_paper", "not_offered", "https://example.org", "none", "2024-01-01"))
            conn.commit()
            conn.close()
            db = Database(path)
            try:
                row = db.conn.execute("SELECT note,expected_count FROM coverage WHERE conference_id='legacy'").fetchone()
                self.assertEqual(row["note"], "kept")
                self.assertIsNone(row["expected_count"])
                zero = db.conn.execute("SELECT expected_count FROM coverage WHERE award_type='best_student_paper'").fetchone()
                self.assertEqual(zero["expected_count"], 0)
            finally:
                db.close()

    def test_multi_conference_year_report_uses_only_known_award_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "report.sqlite3")
            try:
                db.init()
                aaai = db.resolve("AAAI")["id"]
                acl = db.resolve("ACL")["id"]
                db.conn.execute("""INSERT INTO records
                    (id,conference_id,year,award_type,title,status,payload,sources,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    ("paper-1", aaai, 2024, "best_paper", "Paper", "pending", "{}", "[]", "2024", "2024"))
                db.conn.commit()
                db.mark_coverage(aaai, 2024, "best_paper", "partial", "https://example.org/aaai-2024", "official", expected_count=2)
                db.mark_coverage(acl, 2025, "best_student_paper", "not_offered", "https://example.org/acl-2025", "none")
                report = db.coverage_report([aaai, acl], [2024, 2025], offset=0, limit=1)
                self.assertEqual(report["total_rows"], 8)
                self.assertEqual(len(report["rows"]), 1)
                row = report["rows"][0]
                self.assertEqual((row["found_count"], row["expected_count"], row["coverage_rate"]), (1, 2, 50.0))
                summary = report["summary"]
                self.assertEqual((summary["found_total"], summary["known_found"], summary["known_expected"]), (1, 1, 2))
                self.assertEqual((summary["known_targets"], summary["not_offered_targets"], summary["unknown_targets"]), (1, 1, 6))
                self.assertEqual(summary["coverage_rate"], 50.0)
                last = db.coverage_report([aaai, acl], [2024, 2025], offset=7, limit=1)["rows"][0]
                self.assertEqual((last["year"], last["award_type"], last["expected_count"]),
                                 (2025, "best_student_paper", 0))
                db.conn.execute("UPDATE records SET status='rejected' WHERE id='paper-1'")
                db.conn.commit()
                self.assertEqual(db.coverage_report([aaai], [2024])["summary"]["coverage_rate"], 0.0)
            finally:
                db.close()

    def test_total_requires_evidence_and_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "report.sqlite3")
            try:
                db.init()
                cid = db.resolve("AAAI")["id"]
                with self.assertRaises(ValueError):
                    db.mark_coverage(cid, 2024, "best_paper", "partial", "", "note", expected_count=2)
                db.mark_coverage(cid, 2024, "best_paper", "partial", "https://example.org", "note", expected_count=2)
                db.mark_coverage(cid, 2024, "best_paper", "checked", "https://example.org", "note")
                self.assertEqual(db.coverage_report([cid], [2024])["rows"][0]["expected_count"], 2)
                db.mark_coverage(cid, 2024, "best_paper", "partial", "https://example.org", "note", expected_count=None)
                self.assertIsNone(db.coverage_report([cid], [2024])["rows"][0]["expected_count"])
                with self.assertRaisesRegex(ValueError, "正整数"):
                    db.mark_coverage(cid, 2024, "best_paper", "partial", "https://example.org", "note", expected_count=0)
            finally:
                db.close()

    def test_api_query_accepts_multiple_conferences_and_years(self):
        try:
            from api import CoverageQueryReq, query_coverage
        except ImportError as exc:
            self.skipTest(f"API dependencies unavailable: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "report.sqlite3"
            db = Database(path)
            db.init()
            ids = [db.resolve("AAAI")["id"], db.resolve("ACL")["id"]]
            db.close()
            with patch("api.get_db", side_effect=lambda: Database(path)):
                result = query_coverage(CoverageQueryReq(conference_ids=ids, years="2024-2026", limit=2))
            self.assertEqual(result["total_rows"], 12)
            self.assertEqual(len(result["rows"]), 2)
            self.assertIsNone(result["summary"]["coverage_rate"])


if __name__ == "__main__":
    unittest.main()
