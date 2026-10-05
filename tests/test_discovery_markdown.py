import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.discovery import DeepSeekAnthropicWebSearch, OpenAIWebSearch, ResponsesWebSearch, ZhipuWebSearch
from global_cs_paper_awards_agent.llm import LLM
from global_cs_paper_awards_agent.markdown_export import render_markdown
from global_cs_paper_awards_agent.network import crawl

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
        self.assertEqual(llm.model, "deepseek-flash")
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

    def test_search_api_can_reuse_llm_configuration(self):
        with patch.dict(os.environ, {
            "SEARCH_REUSE_LLM": "1", "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "shared-key", "LLM_MODEL": "shared-model",
        }, clear=True):
            search = ResponsesWebSearch()
        self.assertEqual((search.key, search.base, search.model),
                         ("shared-key", "https://api.openai.com/v1", "shared-model"))
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
            return {"status": "completed", "usage": {"input_tokens": 90, "output_tokens": 10, "total_tokens": 100}, "output": [
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
        self.assertEqual(result["token_usage"]["total_tokens"], 100)

    def test_bailian_responses_search_uses_supported_options_and_real_sources(self):
        search = ResponsesWebSearch(api_key="account-key", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                                    model="qwen3.8-max", provider="bailian")
        captured = {}

        def fake_post(body):
            captured.update(body)
            return {"status": "completed", "usage": {"input_tokens": 8, "output_tokens": 3},
                    "output": [{"type": "web_search_call", "action": {"sources": [
                        {"url": "https://conf.example/awards", "title": "Awards"}]}}]}

        search._post = fake_post
        result = search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)
        self.assertEqual(captured["tools"], [{"type": "web_search"}])
        self.assertNotIn("tool_choice", captured)
        self.assertEqual(result["candidates"][0]["url"], "https://conf.example/awards")
        self.assertEqual(result["token_usage"]["provider"], "bailian")

        search._post = lambda _: {"status": "completed", "usage": {"input_tokens": 8, "output_tokens": 3},
                                  "output": [{"type": "message", "content": [{"text": "https://made-up.example"}]}]}
        with self.assertRaisesRegex(ValueError, "未执行网页搜索"):
            search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)

    def test_relay_search_requires_real_responses_web_search(self):
        search = ResponsesWebSearch(api_key="relay-key", base_url="https://relay.example/v1",
                                    model="relay-model", provider="custom")
        conf = {"id": "acl", "acronym": "ACL", "full_name": "ACL"}
        search._post = lambda _: {"status": "completed", "output": [{"type": "message", "content": []}]}
        with self.assertRaisesRegex(ValueError, "中转站未执行 Responses web_search"):
            search.discover(conf, 2026)
        search._post = lambda _: {"status": "completed", "output": [
            {"type": "web_search_call", "action": {"sources": [
                {"url": "https://conf.example/awards", "title": "Awards"}]}}]}
        self.assertEqual(search.discover(conf, 2026)["candidates"][0]["url"],
                         "https://conf.example/awards")

    def test_deepseek_search_uses_anthropic_tool_and_records_account(self):
        search = DeepSeekAnthropicWebSearch(api_key="current-key", base_url="https://api.deepseek.com", model="deepseek-flash")
        captured = {}

        def fake_post(body):
            captured.update(body)
            return {"type": "message", "stop_reason": "end_turn", "usage": {"input_tokens": 40, "output_tokens": 10,
                    "server_tool_use": {"web_search_requests": 1}},
                    "content": [{"type": "server_tool_use", "name": "web_search"},
                                {"type": "web_search_tool_result", "content": [
                                    {"type": "web_search_result", "url": "https://conf.example/awards", "title": "Awards"},
                                    {"type": "web_search_result", "url": "https://conf.example/awards", "title": "Duplicate"},
                                ]}, {"type": "text", "citations": [
                                    {"type": "web_search_result_location", "url": "https://publisher.example/paper", "title": "Paper"}
                                ]}]}

        search._post = fake_post
        result = search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)
        self.assertEqual(captured["tools"], [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}])
        self.assertEqual([item["url"] for item in result["candidates"]],
                         ["https://conf.example/awards", "https://publisher.example/paper"])
        self.assertEqual(result["token_usage"]["provider"], "deepseek")
        self.assertEqual(result["token_usage"]["model"], "deepseek-flash")
        self.assertEqual(result["token_usage"]["total_tokens"], 50)
        self.assertEqual(result["token_usage"]["web_search_requests"], 1)

    def test_deepseek_search_posts_only_to_official_anthropic_endpoint(self):
        search = DeepSeekAnthropicWebSearch(api_key="current-key", base_url="https://api.deepseek.com", model="deepseek-flash")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"type":"message"}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch("global_cs_paper_awards_agent.discovery.urllib.request.build_opener", return_value=opener):
            self.assertEqual(search._post({"model": "deepseek-flash"})["type"], "message")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/anthropic/v1/messages")
        self.assertEqual(request.get_header("X-api-key"), "current-key")
        self.assertNotIn("Authorization", request.headers)

    def test_zhipu_search_uses_current_model_and_structured_tool_sources(self):
        search = ZhipuWebSearch(api_key="current-key", base_url="https://open.bigmodel.cn/api/paas/v4", model="glm-4.6")
        captured = {}

        def fake_post(body):
            captured.update(body)
            return {"usage": {"prompt_tokens": 12, "completion_tokens": 4}, "choices": [{"message": {
                "content": "An uncited answer is not a source",
                "tool_calls": [{"type": "web_search", "search_result": [
                    {"link": "https://conf.example/awards", "title": "Awards"},
                    {"link": "https://conf.example/awards", "title": "Duplicate"},
                ]}],
            }}]}

        search._post = fake_post
        result = search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)
        self.assertEqual(captured["model"], "glm-4.6")
        self.assertEqual(captured["tools"][0]["type"], "web_search")
        self.assertTrue(captured["tools"][0]["web_search"]["search_result"])
        self.assertEqual(result["candidates"], [{"url": "https://conf.example/awards", "title": "Awards"}])
        self.assertEqual(result["token_usage"]["provider"], "zhipu")
        search._post = lambda _: {"choices": [{"message": {"content": "https://invented.example"}}]}
        with self.assertRaisesRegex(ValueError, "未返回可核验"):
            search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)

    def test_deepseek_search_requires_real_tool_results_even_if_text_has_url(self):
        search = DeepSeekAnthropicWebSearch(api_key="key", base_url="https://api.deepseek.com", model="deepseek-flash")
        search._post = lambda _: {"type": "message", "stop_reason": "end_turn",
                                  "usage": {"input_tokens": 3, "output_tokens": 4},
                                  "content": [{"type": "text", "text": "https://made-up.example/awards"}]}
        with self.assertRaisesRegex(ValueError, "未实际调用"):
            search.discover({"id": "acl", "acronym": "ACL", "full_name": "ACL"}, 2026)
        self.assertEqual(search.last_usage["total_tokens"], 7)

    def test_autonomous_candidates_continue_when_one_page_fails(self):
        source = {
            "id": "s1", "url": "https://good.example/awards", "requested_url": "https://good.example/awards",
            "role": "award", "text": "Best Paper Award\nA Valid Paper", "mime": "text/html",
            "retrieved_at": "2026-01-01T00:00:00Z", "acquisition": "http", "extraction_scope": "full document",
        }
        with patch("global_cs_paper_awards_agent.network.Fetcher.fetch", side_effect=[ValueError("unavailable"), (source, [])]):
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
