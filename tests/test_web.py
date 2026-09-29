"""UI interaction tests with Streamlit AppTest, no browser or live LLM needed."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccf_awards.db import Database
from ccf_awards.llm import LLM
from ccf_awards.web_helpers import csv_bytes, export_rows, import_demo, parse_years, run_log_csv_bytes, urls_from_text

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(AppTest is None, "Install requirements-web.txt to test the UI")
class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "web.sqlite3"
        self.env = patch.dict(os.environ, {"CCF_AWARDS_DB":str(self.path), "LLM_API_KEY":"", "LLM_MODEL":"", "DEEPSEEK_API_KEY":"", "LLM_PROVIDER":"deepseek", "GITHUB_TOKEN":"", "GH_TOKEN":""})
        self.env.start()
        self.app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.selectbox(key="provider_name").value, "deepseek")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def demo(self):
        self.button("demo", "导入两条样例").click().run()
        self.assertFalse(self.app.exception)

    def button(self, key, label):
        """Streamlit <1.39 generates form-button keys instead of accepting one."""
        for button in self.app.button:
            if button.key == key or button.label == label:
                return button
        self.fail(f"未找到按钮：{label}")

    def test_unified_ai_settings_and_safe_publish_button(self):
        labels = [item.label for item in self.app.expander]
        self.assertIn("LLM 连接", labels)
        self.assertNotIn("AI 连接设置", labels)
        self.assertNotIn("自动网页搜索设置", labels)
        self.demo()
        self.app.radio(key="section").set_value("记录核验").run()
        self.assertTrue(self.app.text_input(key="publish_password"))
        button = self.button("publish_verified", "验证并发布最新已核验记录到 GitHub")
        self.assertTrue(button.disabled)

    def test_provider_switch_updates_editable_defaults(self):
        self.app.selectbox(key="provider_name").set_value("openai").run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.text_input(key="base_url").value, "https://api.openai.com/v1")
        self.assertEqual(self.app.text_input(key="model_name").value, "")
    def test_batch_collection_controls_accept_multiple_conferences_and_ranges(self):
        self.app.radio(key="section").set_value("采集与导入").run()
        self.assertEqual(self.app.radio(key="collection_mode").value, "自动搜索官网（批量）")
        self.app.multiselect(key="batch_conferences").set_value(["acl-70cc29", "sigkdd-366f1f"])
        self.app.text_input(key="batch_years").set_value("2023-2024, 2026")
        self.assertEqual(parse_years(self.app.text_input(key="batch_years").value), [2026, 2024, 2023])

    def test_empty_state_and_idempotent_demo(self):
        self.assertEqual(self.app.metric[0].value, "190")
        self.assertEqual(self.app.metric[1].value, "0")
        self.demo()
        self.demo()
        self.assertEqual(self.app.metric[1].value, "2")
        self.assertEqual(len(self.app.dataframe[0].value), 2)

    def test_combined_search_matches_same_author(self):
        self.demo()
        self.app.text_input(key="search_author").set_value("Julie")
        self.app.text_input(key="search_affiliation").set_value("Irvine")
        self.button("search_submit", "搜索论文").click().run()
        self.assertEqual(self.app.subheader[0].value, "0 条获奖记录")
        # Start a fresh browser session against the same database. Streamlit
        # 1.37 AppTest cannot reliably change a submitted form field twice.
        self.app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=20).run()
        self.app.text_input(key="search_affiliation").set_value("Stanford")
        self.app.selectbox(key="search_conference").set_value("acl-70cc29")
        self.app.number_input(key="search_year_from").set_value(2020)
        self.app.number_input(key="search_year_to").set_value(2025)
        self.app.text_input(key="search_author").set_value("Julie")
        self.button("search_submit", "搜索论文").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.subheader[0].value, "1 条获奖记录")
        self.assertIn("Mission", self.app.dataframe[0].value.iloc[0]["论文名称"])

    def test_invalid_time_range_is_visible(self):
        self.demo()
        self.app.number_input(key="search_year_from").set_value(2025)
        self.app.number_input(key="search_year_to").set_value(2024)
        self.button("search_submit", "搜索论文").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("起始时间", self.app.error[0].value)

    def test_review_persists_and_does_not_repeat_on_rerun(self):
        self.demo()
        self.app.radio(key="section").set_value("记录核验").run()
        rid = self.app.selectbox(key="review_record").value
        self.app.selectbox(key=f"review_target_{rid}").set_value("verified")
        self.app.text_input(key=f"reviewer_{rid}").set_value("测试核验人")
        self.app.text_area(key=f"review_note_{rid}").set_value("已核对来源")
        self.button("review_submit", "保存核验结论").click().run()
        self.assertFalse(self.app.exception)
        db = Database(self.path)
        try:
            self.assertEqual(len(db.search(status="verified")), 1)
            self.assertEqual(db.conn.execute("SELECT count(*) FROM revisions").fetchone()[0], 1)
        finally:
            db.close()

    def test_save_urls_needs_no_llm(self):
        self.app.radio(key="section").set_value("采集与导入").run()
        self.app.radio(key="collection_mode").set_value("手动网址（单任务）").run()
        self.app.selectbox(key="collect_conference").set_value("acl-70cc29")
        self.app.number_input(key="collect_year").set_value(2024).run()
        self.app.text_area(key="urls_acl-70cc29_2024").set_value("https://2024.aclweb.org/program/best_papers/")
        with patch.object(LLM, "json") as mock_llm:
            self.button("save_urls", "仅保存入口").click().run()
            mock_llm.assert_not_called()
        self.assertFalse(self.app.exception)
        db = Database(self.path)
        try:
            self.assertEqual(len(db.seeds("acl-70cc29", 2024)), 1)
        finally:
            db.close()

    def test_collection_with_mocked_network_and_model(self):
        bundle = json.loads((ROOT / "examples/sample-acl-2024.json").read_text(encoding="utf-8"))
        self.app.radio(key="section").set_value("采集与导入").run()
        self.app.radio(key="collection_mode").set_value("手动网址（单任务）").run()
        self.app.selectbox(key="collect_conference").set_value("acl-70cc29")
        self.app.number_input(key="collect_year").set_value(2024).run()
        self.app.text_input(key="api_key").set_value("temporary-session-secret")
        self.app.text_input(key="model_name").set_value("test-model")
        self.app.text_area(key="urls_acl-70cc29_2024").set_value("https://2024.aclweb.org/program/best_papers/")
        with patch("ccf_awards.network.crawl", return_value=(bundle["sources"], [])), \
             patch.object(LLM, "json", return_value={"records":bundle["records"]}) as model:
            self.button("collect_submit", "开始采集").click().run()
            self.app.run()
            self.assertEqual(model.call_count, 1)
        self.assertFalse(self.app.exception)
        db = Database(self.path)
        try:
            self.assertEqual(len(db.search()), 1)
            self.assertEqual(db.search()[0]["status"], "pending")
            self.assertEqual(db.conn.execute("SELECT count(*) FROM runs").fetchone()[0], 1)
        finally:
            db.close()
        self.assertNotIn(b"temporary-session-secret", self.path.read_bytes())
        self.assertEqual(os.getenv("LLM_API_KEY"), "")

    def test_missing_api_settings_fails_before_network(self):
        self.app.radio(key="section").set_value("采集与导入").run()
        self.app.radio(key="collection_mode").set_value("手动网址（单任务）").run()
        cid = self.app.selectbox(key="collect_conference").value
        year = self.app.number_input(key="collect_year").value
        self.app.text_area(key=f"urls_{cid}_{year}").set_value("https://example.org/2024/awards")
        with patch("ccf_awards.network.crawl") as network:
            self.button("collect_submit", "开始采集").click().run()
            network.assert_not_called()
        self.assertFalse(self.app.exception)
        self.assertTrue(self.app.error)

    def test_coverage_handles_fse_and_unknown_awards(self):
        self.demo()
        self.app.radio(key="section").set_value("采集覆盖").run()
        self.app.selectbox(key="coverage_conference").set_value("acl-70cc29")
        self.app.number_input(key="coverage_from").set_value(2024)
        self.app.number_input(key="coverage_to").set_value(2024)
        self.button("coverage_submit", "查看覆盖情况").click().run()
        self.assertFalse(self.app.exception)
        rows = self.app.dataframe[0].value
        self.assertEqual(set(rows["覆盖状态"]), {"部分记录", "尚未开始"})


    def test_collection_page_shows_seed_coverage_and_token_history(self):
        db = Database(self.path)
        try:
            cid = db.resolve("ACL")["id"]
            db.add_seed(cid, 2024, "https://example.org/2024/awards")
            run_id = db.start_run(cid, 2024)
            db.finish_run(run_id, "extracted", {
                "inserted": 1, "updated": 0, "unchanged": 0,
                "token_usage": {
                    "search": {"total_tokens": 100},
                    "extraction": {"total_tokens": 150},
                },
                "total_tokens": 250,
            })
        finally:
            db.close()
        self.app.radio(key="section").set_value("采集与导入").run()
        self.assertFalse(self.app.exception)
        labels = {metric.label: str(metric.value) for metric in self.app.metric}
        self.assertEqual(labels["已保存入口覆盖"], "1/190 个会议")
        history = self.app.dataframe[0].value
        self.assertIn("搜索 tokens", history.columns)
        self.assertIn("提取 tokens", history.columns)
        self.assertIn("总 tokens", history.columns)
        self.assertEqual(int(history.iloc[0]["总 tokens"]), 250)
class WebHelperTest(unittest.TestCase):
    def test_session_llm_configuration_does_not_change_environment(self):
        with patch.dict(os.environ, {"LLM_API_KEY":"environment-key", "LLM_MODEL":"environment-model"}):
            first = LLM(api_key="first", model="first-model")
            second = LLM(api_key="second", model="second-model")
            self.assertEqual(first.key, "first")
            self.assertEqual(second.key, "second")
            self.assertEqual(LLM().key, "environment-key")

    def test_year_range_parser(self):
        self.assertEqual(parse_years("2023-2025, 2020, 2024"), [2025, 2024, 2023, 2020])
        self.assertEqual(parse_years("2026；2021至2022"), [2026, 2022, 2021])
        with self.assertRaises(ValueError):
            parse_years("2026-2023")
        with self.assertRaises(ValueError):
            parse_years("2024, not-a-year")

    def test_url_list_and_csv_export(self):
        self.assertEqual(urls_from_text("https://example.org\n\nhttps://example.org"), ["https://example.org"])
        with self.assertRaises(ValueError):
            urls_from_text("javascript:alert(1)")
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            try:
                db.init()
                import_demo(db)
                records = db.search()
                csv = csv_bytes(records).decode("utf-8-sig")
                self.assertIn("Stanford University", csv)
                self.assertIn("Best Student Paper Award – Research", csv)
                records[0]["title"] = "=BAD()"
                self.assertIn("'=BAD()", csv_bytes(records).decode("utf-8-sig"))
            finally:
                db.close()

    def test_run_log_csv_export_includes_tokens_and_safe_text(self):
        content = run_log_csv_bytes([{
            "id": 7,
            "acronym": "AAAI",
            "year": 2026,
            "started_at": "2026-09-28T12:00:00",
            "finished_at": "2026-09-28T12:00:03",
            "duration_seconds": 3.0,
            "status": "failed",
            "details": {
                "inserted": 1,
                "updated": 2,
                "unchanged": 3,
                "token_usage": {
                    "search": {"total_tokens": 100},
                    "extraction": {"total_tokens": 150},
                },
                "error": "=unsafe",
            },
        }]).decode("utf-8-sig")
        self.assertIn("任务,会议,年份", content)
        self.assertIn("搜索 tokens,提取 tokens,总 tokens", content)
        self.assertIn("100,150,250", content)
        self.assertIn("'=unsafe", content)


if __name__ == "__main__":
    unittest.main()
