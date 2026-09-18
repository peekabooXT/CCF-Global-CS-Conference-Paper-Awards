import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
from ccf_awards.catalog import load_catalog
from ccf_awards.db import Database
from ccf_awards.model import date_bounds, validate_bundle
from ccf_awards.network import decode_document, public_url
from ccf_awards.llm import LLM
from ccf_awards.__main__ import auto_collect_one, main, collect_one

ROOT = Path(__file__).resolve().parents[1]


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.sqlite3"
        self.db = Database(self.path)
        self.db.init()
        self.bundle = json.loads((ROOT / "examples/sample-acl-2024.json").read_text(encoding="utf-8"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add(self):
        result = self.db.ingest(self.bundle)
        self.assertEqual(result["rejected"], [])
        return self.db.search()[0]["id"]

    def test_catalog_and_ambiguous_fse(self):
        rows = load_catalog()
        self.assertEqual((len(rows), sum(r["rank"] == "A" for r in rows)), (190, 58))
        self.assertEqual(len({r["id"] for r in rows}), 190)
        with self.assertRaisesRegex(ValueError, "歧义"):
            self.db.resolve("FSE")
        self.assertEqual(self.db.resolve("kdd")["acronym"], "SIGKDD")
        self.assertEqual(self.db.resolve("USENIX ATC")["acronym"], "ACM SIGOPS ATC")

    def test_real_examples_validate(self):
        for path in (ROOT / "examples").glob("sample-*.json"):
            b = json.loads(path.read_text(encoding="utf-8"))
            valid, errors = validate_bundle(b, b["conference_id"], b["year"])
            self.assertEqual(errors, [])
            self.assertEqual(len(valid), 1)

    def test_combined_filters_and_author_institution_pair(self):
        self.add()
        self.assertEqual(len(self.db.search(conference=self.bundle["conference_id"], year_from=2023, year_to=2025,
                                            author="JULIE", affiliation="Stanford", award="best_paper", rank="A")), 1)
        self.assertEqual(self.db.search(author="Julie", affiliation="Irvine"), [])
        self.assertEqual(self.db.search(author="Julie", year_to=2023), [])
        self.assertEqual(self.db.search(author="Julie", rank="B"), [])

    def test_date_precision_overlap_and_null(self):
        self.add()
        self.assertEqual(date_bounds("2024-02"), ("2024-02-01", "2024-02-29", "month"))
        self.assertEqual(len(self.db.search(published_from="2024-08-15", published_to="2024-08-16")), 1)
        self.assertEqual(self.db.search(published_from="2024-09-01"), [])
        self.bundle["records"][0]["publication_date"] = None
        self.bundle["records"][0]["publication_date_evidence"] = None
        self.db.ingest(self.bundle)
        self.assertEqual(self.db.search(published_from="2024-01-01"), [])
        with self.assertRaises(ValueError):
            date_bounds("2024-02-30")

    def test_ingest_returns_record_ids_for_result_table(self):
        result = self.db.ingest(self.bundle)
        self.assertEqual(result["record_ids"], [self.db.search()[0]["id"]])

    def test_persistent_run_history_includes_duration_and_details(self):
        run_id = self.db.start_run(self.bundle["conference_id"], 2024)
        self.db.finish_run(run_id, "no_results", {"inserted": 0, "record_ids": []})
        row = self.db.runs(1)[0]
        self.assertEqual((row["id"], row["acronym"], row["status"]), (run_id, "ACL", "no_results"))
        self.assertGreaterEqual(row["duration_seconds"], 0)
        self.assertEqual(row["details"]["inserted"], 0)

    def test_discovery_failure_is_written_to_run_history(self):
        class FailingSearch:
            def discover(self, conference, year, limit):
                raise ValueError("search unavailable")
        with self.assertRaisesRegex(ValueError, "search unavailable"):
            auto_collect_one(self.db, self.db.resolve("ACL"), 2026,
                             search=FailingSearch(), llm=object())
        row = self.db.runs(1)[0]
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["details"]["stage"], "discovery")
    def test_duplicate_preserves_review_and_change_archives(self):
        rid = self.add()
        self.db.review(rid, "verified", "Tester", "Compared the source")
        self.assertEqual(self.db.ingest(self.bundle)["unchanged"], 1)
        self.assertEqual(self.db.search()[0]["status"], "verified")
        self.bundle["records"][0]["authors"][0]["affiliations"] = []
        self.assertEqual(self.db.ingest(self.bundle)["updated"], 1)
        self.assertEqual(self.db.search()[0]["status"], "pending")
        self.assertEqual(self.db.conn.execute("SELECT count(*) FROM revisions").fetchone()[0], 2)

    def test_reject_nonexistent_evidence(self):
        self.bundle["records"][0]["award_evidence"]["quote"] = "Best Paper Awards Fabricated Winning Paper"
        result = self.db.ingest(self.bundle)
        self.assertEqual(result["inserted"], 0)
        self.assertEqual(len(result["rejected"]), 1)

    def test_reject_unsupported_awards_and_unlinked_heading(self):
        self.bundle["records"][0]["award_name"] = "Outstanding Paper Award"
        self.assertEqual(len(self.db.ingest(self.bundle)["rejected"]), 1)
        self.bundle["records"][0]["award_name"] = "Best Paper Awards"
        self.bundle["records"][0]["award_evidence"]["quote"] = "Best Paper Awards"
        self.assertEqual(len(self.db.ingest(self.bundle)["rejected"]), 1)

    def test_no_results_never_means_award_not_offered(self):
        self.bundle["records"] = []
        self.db.ingest(self.bundle)
        rows = self.db.coverage(2024, 2024, self.bundle["conference_id"])
        self.assertEqual({r["state"] for r in rows}, {"not_started"})

    def test_coverage_contradictions_and_invalidation(self):
        self.add()
        with self.assertRaisesRegex(ValueError, "不能标记"):
            self.db.mark_coverage(self.bundle["conference_id"], 2024, "best_paper", "not_offered", "https://example.org/2024", "test")
        self.db.mark_coverage(self.bundle["conference_id"], 2024, "best_paper", "checked", "https://example.org/2024", "test")
        self.bundle["records"][0]["authors"] = []
        self.db.ingest(self.bundle)
        row = self.db.coverage(2024, 2024, self.bundle["conference_id"])[0]
        self.assertEqual(row["state"], "partial")

    def test_punctuation_in_paper_identity(self):
        self.bundle["sources"][0]["text"] = "Best Paper Awards\nC++\nBest Paper Awards\nC#"
        first = self.bundle["records"][0]
        first.update(title="C++", title_evidence={"source_id":"s1", "quote":"C++"},
                     award_evidence={"source_id":"s1", "quote":"Best Paper Awards\nC++"})
        second = copy.deepcopy(first)
        second.update(title="C#", title_evidence={"source_id":"s1", "quote":"C#"},
                      award_evidence={"source_id":"s1", "quote":"Best Paper Awards\nC#"})
        self.bundle["records"].append(second)
        self.assertEqual(self.db.ingest(self.bundle)["inserted"], 2)

    def test_json_import_cannot_self_verify(self):
        self.bundle["records"][0]["status"] = "verified"
        self.add()
        self.assertEqual(self.db.search()[0]["status"], "pending")

    def test_sql_and_wildcards_are_literal(self):
        self.add()
        self.assertEqual(self.db.search(title="%' OR 1=1 --"), [])
        self.assertEqual(self.db.search(author="%"), [])

    def test_wrong_year_rejected(self):
        self.bundle["year"] = 2023
        with self.assertRaisesRegex(ValueError, "年份"):
            self.db.ingest(self.bundle)

    def test_private_url_blocked(self):
        for url in ("http://127.0.0.1/x", "http://[::1]/", "http://169.254.169.254/"):
            with self.assertRaises(ValueError):
                public_url(url)

    def test_default_search_hides_rejected(self):
        rid = self.add()
        self.db.review(rid, "rejected", "Tester", "Incorrect award mapping")
        self.assertEqual(self.db.search(), [])
        self.assertEqual(len(self.db.search(status="all")), 1)

    def test_bad_import_root_fails_cleanly(self):
        for bundle in ([], {}, {"conference_id":None}, {"conference_id":"ACL", "year":True}):
            with self.assertRaises(ValueError):
                self.db.ingest(bundle)

    def test_pdf_metadata_limits_pages(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        except ImportError:
            self.skipTest("optional pypdf not installed")
        writer = PdfWriter()
        for number in range(1, 5):
            page = writer.add_blank_page(width=612, height=792)
            font = DictionaryObject({NameObject("/Type"):NameObject("/Font"),
                                     NameObject("/Subtype"):NameObject("/Type1"),
                                     NameObject("/BaseFont"):NameObject("/Helvetica")})
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"):font})})
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 50 700 Td (Metadata page number {number}) Tj ET".encode())
            page[NameObject("/Contents")] = writer._add_object(stream)
        target = io.BytesIO()
        writer.write(target)
        text, _ = decode_document(target.getvalue(), "application/pdf", "utf-8", "https://example.org/paper.pdf", 3)
        self.assertIn("Metadata page number 3", text)
        self.assertNotIn("Metadata page number 4", text)

    def test_html_cleaning_and_relative_links(self):
        raw = b'<html><script>do bad things</script><h2>Best Paper Award</h2><p>Winner One</p><a href="/paper.pdf">Paper PDF</a></html>'
        text, links = decode_document(raw, "text/html", "utf-8", "https://example.org/2024/")
        self.assertNotIn("do bad things", text)
        self.assertIn("Best Paper Award\nWinner One", text)
        self.assertEqual(links[0]["url"], "https://example.org/paper.pdf")

    def test_collect_to_sqlite_with_mocked_api_and_fetch(self):
        # Simulated network/model, real coordinator -> validator -> SQLite -> search.
        with patch.dict(os.environ, {"LLM_API_KEY":"test-secret", "LLM_MODEL":"test-model"}), \
             patch("ccf_awards.network.crawl", return_value=(self.bundle["sources"], [])), \
             patch.object(LLM, "json", return_value={"records":self.bundle["records"]}), redirect_stderr(io.StringIO()):
            result = collect_one(self.db, self.db.resolve("ACL"), 2024, ["https://example.org/2024"])
        self.assertEqual(result["inserted"], 1)
        self.assertTrue(Path(result["raw_bundle"]).exists())
        self.assertEqual(self.db.conn.execute("SELECT status FROM runs").fetchone()[0], "extracted")
        self.assertEqual(len(self.db.search(author="Julie")), 1)

    def test_failed_collection_logged(self):
        with patch.dict(os.environ, {"LLM_API_KEY":"test-secret", "LLM_MODEL":"test-model"}), \
             patch("ccf_awards.network.crawl", side_effect=ValueError("fetch failed")):
            with self.assertRaises(ValueError):
                collect_one(self.db, self.db.resolve("ACL"), 2024, ["https://example.org/2024"])
        self.assertEqual(self.db.conn.execute("SELECT status FROM runs").fetchone()[0], "failed")
        self.assertEqual(self.db.search(), [])

    def test_cli_exit_codes_and_csv(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = main(["--db", str(self.path), "demo"])
            self.assertEqual(code, 0)
            csv_path = Path(self.tmp.name) / "results.csv"
            code = main(["--db", str(self.path), "search", "--author", "Julie", "--csv", str(csv_path)])
            self.assertEqual(code, 0)
            self.assertIn("Stanford University", csv_path.read_text(encoding="utf-8-sig"))
            code = main(["--db", str(self.path), "search", "--year-from", "2025", "--year-to", "2024"])
            self.assertEqual(code, 2)

    def test_api_request_json_contract_and_credentials_not_saved(self):
        class Response(io.BytesIO):
            pass
        response = Response(json.dumps({"choices":[{"finish_reason":"stop", "message":{"content":"{\"records\": []}"}}]}).encode())
        with patch.dict(os.environ, {"LLM_API_KEY":"test-secret", "LLM_MODEL":"test-model", "LLM_BASE_URL":"https://api.example.org/v1"}), \
             patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = response
            result = LLM().json("Output JSON", {"sources":[]})
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.example.org/v1/chat/completions")
            self.assertEqual(json.loads(request.data)["response_format"], {"type":"json_object"})
            self.assertNotIn("test-secret", request.data.decode())
            self.assertEqual(result, {"records":[]})


if __name__ == "__main__":
    unittest.main()
