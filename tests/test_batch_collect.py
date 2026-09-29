import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.__main__ import collect_one
from ccf_awards.db import Database
from ccf_awards.discovery import ResponsesWebSearch
from ccf_awards.llm import LLM


class BatchCollectCoreTest(unittest.TestCase):
    def test_selected_award_scopes_search_and_extraction_prompts(self):
        conference = {"id": "example", "acronym": "EX", "full_name": "Example Conference"}
        llm = LLM(provider="custom", api_key="key", base_url="https://example.org/v1", model="model")
        with patch.object(llm, "json", return_value={"records": []}) as request:
            llm.extract(conference, 2026, [{"text": "sample", "role": "award"}],
                        award_types=["best_student_paper"])
        allowed = request.call_args.args[1]["allowed_award_names_case_insensitive"]
        self.assertIn("best student paper award", allowed)
        self.assertNotIn("best paper award", allowed)

        search = ResponsesWebSearch(api_key="key", base_url="https://example.org/v1", model="model")
        with patch.object(search, "_post", return_value={"output": []}) as request:
            search.discover(conference, 2026, award_types=["best_student_paper"])
        prompt = request.call_args.args[0]["input"]
        self.assertIn("Best Student Paper Award", prompt)
        self.assertNotIn("or Best Paper Award", prompt)

    def test_selected_award_is_enforced_before_ingest(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")

                class FakeLLM:
                    last_usage = None

                    def extract(self, conference, year, sources, award_types=None):
                        self.selected = award_types
                        return {"conference_id": conference["id"], "year": year,
                                "sources": sources, "records": [
                                    {"title": "First", "award_name": "Best Paper Award"},
                                    {"title": "Second", "award_name": "Best Student Paper Award"},
                                ]}

                llm = FakeLLM()
                with patch.object(db, "ingest", return_value={"inserted": 1, "updated": 0,
                                                            "unchanged": 0, "rejected": [], "record_ids": []}) as ingest:
                    result = collect_one(db, conf, 2026, [],
                                         local_sources=[{"text": "sample", "role": "award"}],
                                         llm=llm, award_types=["best_student_paper"],
                                         output=str(Path(temp) / "out.json"), notify=lambda _: None)
                self.assertEqual(llm.selected, {"best_student_paper"})
                self.assertEqual([r["title"] for r in ingest.call_args.args[0]["records"]], ["Second"])
                self.assertEqual(result["award_types"], ["best_student_paper"])
                saved = json.loads((Path(temp) / "out.json").read_text(encoding="utf-8"))
                self.assertEqual([r["title"] for r in saved["records"]], ["Second"])
            finally:
                db.close()

    def test_batch_continues_after_missing_saved_entrance(self):
        try:
            from api import BatchCollectReq, LLMConfig, _do_batch_collect
        except ImportError as exc:
            self.skipTest(f"API test dependencies unavailable: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")
                other = db.resolve("ACL")
                db.add_seed(conf["id"], 2025, "https://example.org/2025-awards")
                db.add_seed(other["id"], 2025, "https://example.org/acl-2025-awards")
                db.add_seed(other["id"], 2026, "https://example.org/acl-2026-awards")
                req = BatchCollectReq(conference_ids=[conf["id"], other["id"]], years="2025-2026",
                                      strategy="urls", award_types=["best_paper"],
                                      llm=LLMConfig(provider="custom", api_key="test-key",
                                                    base_url="https://example.org/v1", model="test-model"))
                events = []
                with patch("api._do_collect", return_value={"status": "extracted", "inserted": 1,
                                                             "updated": 0, "unchanged": 0}) as collect:
                    result = _do_batch_collect(db, req, events.append)
                self.assertEqual(result["total"], 4)
                self.assertEqual(result["completed"], 3)
                self.assertEqual(result["failed"], 1)
                self.assertEqual(collect.call_count, 3)
                self.assertEqual(collect.call_args.args[1].award_types, ["best_paper"])
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM runs WHERE status='failed'").fetchone()[0], 1)
                self.assertEqual(len([e for e in events if isinstance(e, dict) and e.get("type") == "task"]), 8)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
