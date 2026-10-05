import unittest
from unittest.mock import MagicMock, patch

from global_cs_paper_awards_agent.model_catalog import _catalog_url, list_provider_models
from global_cs_paper_awards_agent.providers import provider_profile


class ModelCatalogTest(unittest.TestCase):
    def test_named_provider_defaults(self):
        self.assertEqual(provider_profile("deepseek")[1]["model"], "deepseek-flash")
        self.assertEqual(provider_profile("bailian")[1]["key_env"], "DASHSCOPE_API_KEY")
        self.assertEqual(provider_profile("qwen")[1]["key_env"], "DASHSCOPE_API_KEY")
        self.assertEqual(provider_profile("zhipu")[1]["base_url"], "https://open.bigmodel.cn/api/paas/v4")

    def test_model_urls_are_restricted_to_provider_hosts(self):
        self.assertEqual(_catalog_url("deepseek", None), "https://api.deepseek.com/models")
        self.assertIn("providers=qwen", _catalog_url("qwen", None))
        with self.assertRaisesRegex(ValueError, "官方 HTTPS"):
            _catalog_url("deepseek", "https://api.deepseek.com.evil.test")
        with self.assertRaisesRegex(ValueError, "官方 HTTPS"):
            _catalog_url("openai", "http://api.openai.com/v1")
        with self.assertRaisesRegex(ValueError, "公共 HTTPS"):
            _catalog_url("custom", "http://example.org/v1")
        with self.assertRaisesRegex(ValueError, "公共互联网"):
            _catalog_url("custom", "https://127.0.0.1/v1")
        with patch("global_cs_paper_awards_agent.model_catalog.public_url", return_value="https://relay.example/v1") as validate:
            self.assertEqual(_catalog_url("custom", "https://relay.example/v1"),
                             "https://relay.example/v1/models")
        validate.assert_called_once_with("https://relay.example/v1")

    def test_relay_model_list_uses_current_key_and_public_url_guard(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data":[{"id":"relay-model"}]}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch("global_cs_paper_awards_agent.model_catalog.public_url", return_value="https://relay.example/v1"), \
             patch("global_cs_paper_awards_agent.model_catalog.urllib.request.build_opener", return_value=opener):
            models = list_provider_models("custom", "relay-key", "https://relay.example/v1")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://relay.example/v1/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer relay-key")
        self.assertEqual(models, [{"id": "relay-model", "name": "relay-model"}])
        self.assertNotIn("relay-key", str(models))

    def test_live_models_use_current_key_without_returning_it(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"data":[{"id":"deepseek-flash","name":"Flash"},{"id":"deepseek-v4-pro"}]}'
        )
        opener = MagicMock()
        opener.open.return_value = response
        with patch("global_cs_paper_awards_agent.model_catalog.urllib.request.build_opener", return_value=opener):
            models = list_provider_models("deepseek", "current-key")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/models")
        self.assertEqual(request.get_header("Authorization"), "Bearer current-key")
        self.assertEqual(models, [{"id": "deepseek-flash", "name": "Flash"},
                                  {"id": "deepseek-v4-pro", "name": "deepseek-v4-pro"}])
        self.assertNotIn("current-key", str(models))

    def test_bailian_model_list_parses_official_response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'{"output":{"models":[{"model":"qwen3.8-max","name":"Qwen Max"}]}}'
        )
        opener = MagicMock()
        opener.open.return_value = response
        with patch("global_cs_paper_awards_agent.model_catalog.urllib.request.build_opener", return_value=opener):
            models = list_provider_models("qwen", "dashscope-key")
        self.assertEqual(models, [{"id": "qwen3.8-max", "name": "Qwen Max"}])
