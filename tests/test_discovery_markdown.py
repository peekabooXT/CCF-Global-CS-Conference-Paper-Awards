import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.db import Database
from ccf_awards.discovery import OpenAIWebSearch, ResponsesWebSearch
from ccf_awards.llm import LLM
from ccf_awards.markdown_export import render_markdown
from ccf_awards.network import crawl

ROOT = Path(__file__).resolve().parents[1]


class DiscoveryAndMarkdownTest(unittest.TestCase):
    def test_deepseek_is_default_extraction_provider(self):
        with patch.dict(os.environ, {
            "DEEPSEEK_API_KEY": "deepseek-key",
            "LLM_API_KEY": "", "LLM_BASE_URL": "", "LLM_MODEL": "", "LLM_PROVIDER": "deepseek",
        }, clear=True):
            llm = LLM()
        self.assertEqual(llm.provider, "deepseek")
        self.assertEqual(llm.base, "https://api.deepseek.com")
        self.assertEqual(llm.model, "deepseek-chat")
        self.assertEqual(llm.key, "deepseek-key")

    def test_named_and_custom_provider_overrides(self):
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "openai-key", "LLM_PROVIDER": "openai", "LLM_MODEL": "account-model",
        }, clear=True):
            llm = LLM()
        self.assertEqual((llm.provider, llm.base, llm.model, llm.key),
                         ("openai", "https://api.openai.com/v1", "account-model", "openai-key"))
        custom = LLM(provider="custom", api_key="custom-key", base_url="https://llm.example/v1", model="custom-model")
        self.assertEqual((custom.provider, custom.base, custom.model),
                         ("custom", "https://llm.example/v1", "custom-model"))

    def test_search_api_has_independent_configuration(self):
        with patch.dict(os.environ, {
            "SEARCH_API_KEY": "search-key", "SEARCH_BASE_URL": "https://search.example/v1",
            "SEARCH_MODEL": "search-model", "DEEPSEEK_API_KEY": "deepseek-key",
        }, clear=True):
            search = ResponsesWebSearch()
            llm = LLM()
        self.assertEqual((search.key, search.base, search.model),
                         ("search-key", "https://search.example/v1", "search-model"))
        self.assertEqual(llm.provider, "deepseek")
    def test_sources_include_search_and_message_citations_without_duplicates(self):
        response = {
            "output": [
                {"type": "web_search_call", "action": {"sources": [
                    {"url": "https://conf.example/awards", "title": "Awards"},
                    {"url": "https://conf.example/awards", "title": "Duplicate"},
                ]}},
                {"type": "message", "content": [{"annotations": [
                    {"type": "url_citation", "url": "https://publisher.example/paper", "title": "Paper"}
                ]}]},
            ]
        }
        self.assertEqual(OpenAIWebSearch._sources(response), [
            {"url": "https://conf.example/awards", "title": "Awards"},
            {"url": "https://publisher.example/paper", "title": "Paper"},
        ])

    def test_discover_requires_web_search_and_source_details(self):
        search = OpenAIWebSearch(api_key="test", base_url="https://api.openai.com/v1", model="test-model")
        captured = {}

        def fake_post(body):
            captured.update(body)
            return {"status": "completed", "output": [
                {"type": "web_search_call", "action": {"sources": [
                    {"url": "https://conf.example/2026/awards", "title": "Official awards"}
                ]}}
            ]}

        search._post = fake_post
        conference = {"id": "acl-test", "acronym": "ACL", "full_name": "Annual Meeting of ACL"}
        result = search.discover(conference, 2026, 1)
        self.assertEqual(captured["tools"], [{"type": "web_search"}])
        self.assertEqual(captured["tool_choice"], "required")
        self.assertIn("web_search_call.action.sources", captured["include"])
        self.assertFalse(captured["store"])
        self.assertEqual(result["candidates"][0]["url"], "https://conf.example/2026/awards")

    def test_autonomous_candidates_continue_when_one_page_fails(self):
        source = {
            "id": "s1", "url": "https://good.example/awards", "requested_url": "https://good.example/awards",
            "role": "award", "text": "Best Paper Award\nA Valid Paper", "mime": "text/html",
            "retrieved_at": "2026-01-01T00:00:00Z", "acquisition": "http", "extraction_scope": "full document",
        }
        with patch("ccf_awards.network.Fetcher.fetch", side_effect=[ValueError("unavailable"), (source, [])]):
            sources, warnings = crawl(
                ["https://bad.example/awards", "https://good.example/awards"],
                max_pages=2,
                strict_seeds=False,
            )
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(warnings), 1)
        self.assertFalse(warnings[0]["required"])
    def test_render_markdown_creates_four_views_with_affiliations(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            db = Database(temp / "awards.sqlite3")
            db.init()
            for sample in sorted((ROOT / "examples").glob("sample-*.json")):
                db.ingest(json.loads(sample.read_text(encoding="utf-8")))
            result = render_markdown(db, temp)
            db.close()

            self.assertEqual(result["records"], 2)
            expected = [
                temp / "AWARDS.md",
                temp / "docs/awards/BY_CATEGORY.md",
                temp / "docs/awards/BY_YEAR.md",
                temp / "docs/awards/BY_AWARD.md",
            ]
            self.assertTrue(all(path.exists() for path in expected))
            main = expected[0].read_text(encoding="utf-8")
            self.assertIn("会议/期刊字母排序", main)
            self.assertIn("作者及单位", main)
            self.assertIn("Stanford University", main)
            self.assertLess(main.index("| ACL |"), main.index("| SIGKDD |"))
            self.assertIn("[会议/期刊类别分类检索](docs/awards/BY_CATEGORY.md)", main)


if __name__ == "__main__":
    unittest.main()
