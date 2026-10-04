import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.__main__ import auto_collect_one, collect_one
from ccf_awards.db import Database
from ccf_awards.discovery import ResponsesWebSearch
from ccf_awards.llm import LLM


class BatchCollectCoreTest(unittest.TestCase):
    def test_replace_saved_urls_requires_current_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                cid = db.resolve("AAAI")["id"]
                old = "https://example.org/old-2025-awards"
                new = "https://example.org/new-2025-awards"
                db.add_seed(cid, 2025, old)
                with self.assertRaisesRegex(ValueError, "重新核对"):
                    db.replace_seeds(cid, 2025, [], [new])
                self.assertEqual(db.seeds(cid, 2025), [old])
                self.assertEqual(db.replace_seeds(cid, 2025, [old], [new]), [new])
                self.assertEqual(db.seeds(cid, 2025), [new])
                with self.assertRaisesRegex(ValueError, "URL"):
                    db.replace_seeds(cid, 2025, [new], ["javascript:bad"])
                self.assertEqual(db.seeds(cid, 2025), [new])
            finally:
                db.close()

    def test_auto_search_prefers_saved_urls_and_returns_review_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")
                saved = "https://example.org/saved-2025-awards"
                candidate = "https://example.org/found-2025-awards"
                db.add_seed(conf["id"], 2025, saved)

                class Search:
                    last_usage = {"total_tokens": 42}

                    def discover(self, conference, year, limit):
                        return {"candidates": [{"url": candidate}], "token_usage": self.last_usage}

                def collect(*args, **kwargs):
                    self.assertEqual(args[3], [saved, candidate])
                    return {"seed_review": kwargs["run_details"]["seed_review"]}

                with patch("ccf_awards.__main__.collect_one", side_effect=collect):
                    result = auto_collect_one(db, conf, 2025, output_dir=temp,
                                              search=Search(), llm=object(), notify=lambda _: None)
                self.assertEqual(result["seed_review"]["saved_urls"], [saved])
                self.assertEqual(result["seed_review"]["candidate_urls"], [candidate])
                self.assertEqual(db.seeds(conf["id"], 2025), [saved])
            finally:
                db.close()

    def test_auto_search_failure_falls_back_to_saved_url(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                conf = db.resolve("AAAI")
                saved = "https://example.org/saved-2025-awards"
                db.add_seed(conf["id"], 2025, saved)

                class Search:
                    last_usage = None

                    def discover(self, conference, year, limit):
                        raise ValueError("search unavailable")

                def collect(*args, **kwargs):
                    self.assertEqual(args[3], [saved])
                    return {"seed_review": kwargs["run_details"]["seed_review"]}

                with patch("ccf_awards.__main__.collect_one", side_effect=collect):
                    result = auto_collect_one(db, conf, 2025, output_dir=temp,
                                              search=Search(), llm=object(), notify=lambda _: None)
                self.assertIn("search unavailable", result["seed_review"]["search_error"])
            finally:
                db.close()

    def test_server_retains_per_batch_task_limit(self):
        try:
            from api import BatchCollectReq, LLMConfig, SeedLookupReq, _do_batch_collect, lookup_seeds
        except ImportError as exc:
            self.skipTest(f"API test dependencies unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "100"):
            lookup_seeds(SeedLookupReq(conference_ids=["a", "b"], years=list(range(1950, 2001))))
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                ids = [row["id"] for row in db.conferences()[:101]]
                req = BatchCollectReq(conference_ids=ids, years="2025", strategy="auto",
                                      llm=LLMConfig(provider="custom", api_key="key",
                                                    base_url="https://example.org/v1", model="model"))
                with self.assertRaisesRegex(ValueError, "100"):
                    _do_batch_collect(db, req, lambda _: None)
            finally:
                db.close()

    def test_lookup_saved_urls_for_selected_targets(self):
        try:
            from api import SeedLookupReq, lookup_seeds
        except ImportError as exc:
            self.skipTest(f"API test dependencies unavailable: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.sqlite3"
            db = Database(path)
            db.init()
            aaai = db.resolve("AAAI")["id"]
            acl = db.resolve("ACL")["id"]
            db.add_seed(aaai, 2025, "https://example.org/aaai-2025")
            db.add_seed(aaai, 2025, "https://example.org/another-page")
            db.close()
            with patch("api.get_db", side_effect=lambda: Database(path)):
                result = lookup_seeds(SeedLookupReq(conference_ids=[aaai, acl], years=[2025]))
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(len(result["items"][0]["urls"]), 2)
            self.assertEqual(result["items"][1]["urls"], [])

    def test_replace_saved_urls_api_requires_explicit_confirmation(self):
        try:
            from api import ReplaceSeedReq, replace_seeds
        except ImportError as exc:
            self.skipTest(f"API test dependencies unavailable: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.sqlite3"
            db = Database(path)
            db.init()
            cid = db.resolve("AAAI")["id"]
            db.close()
            payload = dict(conference_id=cid, year=2025, expected_urls=[],
                           urls=["https://example.org/awards-2025"])
            with patch("api.get_db", side_effect=lambda: Database(path)):
                with self.assertRaisesRegex(ValueError, "确认"):
                    replace_seeds(ReplaceSeedReq(**payload))
                result = replace_seeds(ReplaceSeedReq(**payload, confirmed=True))
            self.assertEqual(result["urls"], payload["urls"])

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
