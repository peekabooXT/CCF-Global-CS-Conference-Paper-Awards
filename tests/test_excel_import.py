"""Integration tests for the curated Excel-to-SQLite import path."""
import tempfile
import unittest
from pathlib import Path

from ccf_awards.db import Database
from ccf_awards.excel_import import import_excel

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "data" / "exports" / "CCF190_2023-2026截至2026-09-15_论文奖核验整理版.xlsx"


class ExcelImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "awards.sqlite3")
        self.db.init()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_import_is_complete_searchable_and_idempotent(self):
        first = import_excel(self.db, WORKBOOK)
        self.assertEqual(first["inserted"], 325)
        self.assertEqual(len(self.db.search(status="all")), 325)
        self.assertEqual(len(self.db.search(award="best_paper", status="all")), 289)
        self.assertEqual(len(self.db.search(award="best_student_paper", status="all")), 36)
        self.assertEqual(len(self.db.search(year_from=2026, year_to=2026, status="all")), 57)
        matched = self.db.search(author="Jiaying Zhu", affiliation="Chinese University", status="all")
        self.assertEqual(len(matched), 1)
        self.assertIn("Miter-Aware LUT Mapping", matched[0]["title"])
        podc = self.db.search(conference=self.db.resolve("PODC")["id"], year_from=2026, year_to=2026,
                              award="best_student_paper", status="all")
        self.assertEqual(len(podc), 1)
        second = import_excel(self.db, WORKBOOK)
        self.assertEqual(second["unchanged"], 325)
        self.assertEqual(second["inserted"], 0)

    def test_manual_review_survives_reimport(self):
        import_excel(self.db, WORKBOOK)
        record_id = self.db.search(status="all")[0]["id"]
        self.db.review(record_id, "rejected", "Human reviewer", "Manual correction")
        import_excel(self.db, WORKBOOK)
        record = next(item for item in self.db.search(status="all") if item["id"] == record_id)
        self.assertEqual(record["status"], "rejected")
        self.assertEqual(record["reviewer"], "Human reviewer")


if __name__ == "__main__":
    unittest.main()