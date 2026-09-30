"""Official-page discovery through a Responses API with a real web_search tool."""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .model import url_syntax
from .network import NoRedirect
from .providers import provider_profile
from .usage import normalize_usage


class ResponsesWebSearch:
    """Find candidate official award pages; fetching and validation happen later."""

    def __init__(self, api_key=None, base_url=None, model=None, provider=None):
        reuse = os.getenv("SEARCH_REUSE_LLM", "0") == "1"
        if reuse and api_key is None and base_url is None and model is None:
            _, profile = provider_profile(os.getenv("LLM_PROVIDER", "deepseek"))
            self.key = os.getenv("LLM_API_KEY", "") or os.getenv(profile["key_env"], "")
            self.base = (os.getenv("LLM_BASE_URL", "") or profile["base_url"]).rstrip("/")
            self.model = os.getenv("LLM_MODEL", "") or profile["model"]
        else:
            self.key = api_key if api_key is not None else os.getenv("SEARCH_API_KEY", os.getenv("OPENAI_API_KEY", ""))
            self.base = (base_url if base_url is not None else os.getenv("SEARCH_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))).rstrip("/")
            self.model = model if model is not None else os.getenv("SEARCH_MODEL", os.getenv("OPENAI_SEARCH_MODEL", ""))
        if not self.key or not self.model:
            raise ValueError("自主搜索需要可复用的 LLM 连接，或 SEARCH_API_KEY 和 SEARCH_MODEL")
        url_syntax(self.base)
        if urlsplit(self.base).scheme != "https":
            raise ValueError("SEARCH_BASE_URL 必须使用 HTTPS")
        self.provider = provider or urlsplit(self.base).hostname
        self.last_usage = None

    def _post(self, body):
        request = urllib.request.Request(
            self.base + "/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
        )
        opener = urllib.request.build_opener(NoRedirect())
        for attempt in range(3):
            try:
                with opener.open(request, timeout=120) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("网页搜索 API 响应超过 8 MiB")
                return json.loads(raw)
            except urllib.error.HTTPError as exc:
                if attempt < 2 and (exc.code == 429 or 500 <= exc.code < 600):
                    time.sleep(1 + attempt)
                    continue
                raise ValueError(f"搜索 Responses API HTTP {exc.code}；请检查模型的 web_search 权限和额度") from None
            except (urllib.error.URLError, TimeoutError):
                raise ValueError("搜索 Responses API 网络失败或超时") from None
            except json.JSONDecodeError:
                raise ValueError("搜索 Responses API 返回了无效 JSON") from None

    @staticmethod
    def _sources(response):
        found = []
        seen = set()

        def add(url, title=""):
            if not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in seen:
                return
            seen.add(url)
            found.append({"url": url, "title": str(title or "").strip()})

        for item in response.get("output", []):
            if item.get("type") == "web_search_call":
                for source in (item.get("action") or {}).get("sources", []):
                    add(source.get("url"), source.get("title"))
            if item.get("type") == "message":
                for content in item.get("content", []):
                    for annotation in content.get("annotations", []):
                        if annotation.get("type") == "url_citation":
                            add(annotation.get("url"), annotation.get("title"))
        return found

    def discover(self, conference, year, limit=5, award_types=None):
        if not 1 <= limit <= 10:
            raise ValueError("候选网址数量应在 1–10 之间")
        selected = set(award_types or ("best_paper", "best_student_paper"))
        if not selected or not selected.issubset({"best_paper", "best_student_paper"}):
            raise ValueError("请选择最佳论文奖或最佳学生论文奖")
        targets = [label for key, label in (("best_paper", "Best Paper Award"),
                                            ("best_student_paper", "Best Student Paper Award")) if key in selected]
        prompt = f"""Find official web pages for {conference['full_name']} ({conference['acronym']}) {year}
that explicitly announce {' or '.join(targets)} winners.
Prioritize the conference website and the official publisher/society website.
Do not use social media, scraped award aggregators, or search-result snippets as evidence.
Return a short answer with the strongest official pages."""
        body = {
            "model": self.model,
            "instructions": "Use web search to locate official sources only. Candidate URLs will be fetched and independently validated by another component.",
            "input": prompt,
            "tools": [{"type": "web_search"}],
            "tool_choice": "required",
            "include": ["web_search_call.action.sources"],
            "max_tool_calls": 3,
            "store": False,
        }
        if self.provider in ("bailian", "qwen"):
            # Model Studio Responses does not support forced search or these OpenAI options.
            for key in ("tool_choice", "include", "max_tool_calls", "store"):
                body.pop(key)
        response = self._post(body)
        self.last_usage = normalize_usage(response, self.provider, self.model)
        if response.get("status") not in (None, "completed"):
            raise ValueError("网页搜索响应未完整结束")
        if self.provider in ("bailian", "qwen") and not any(
                item.get("type") == "web_search_call" for item in response.get("output", [])):
            raise ValueError("当前百炼模型未执行网页搜索；请换支持 Responses web_search 的模型或使用已有网址")
        return {
            "conference_id": conference["id"],
            "conference": conference["acronym"],
            "year": year,
            "model": self.model,
            "candidates": self._sources(response)[:limit],
            "token_usage": self.last_usage,
        }


class DeepSeekAnthropicWebSearch(ResponsesWebSearch):
    """Use the active DeepSeek connection via its Anthropic Messages API."""

    def __init__(self, api_key, base_url, model):
        super().__init__(api_key=api_key, base_url=base_url, model=model, provider="deepseek")
        if urlsplit(self.base).hostname != "api.deepseek.com":
            raise ValueError("DeepSeek 网页搜索仅支持官方 API 地址")

    def _post(self, body):
        request = urllib.request.Request(
            "https://api.deepseek.com/anthropic/v1/messages",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=120) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("网页搜索 API 响应超过 8 MiB")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"DeepSeek 网页搜索 HTTP {exc.code}；请检查模型、Key 和账户额度") from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("DeepSeek 网页搜索网络失败或超时") from None
        except json.JSONDecodeError:
            raise ValueError("DeepSeek 网页搜索返回了无效 JSON") from None

    @staticmethod
    def _sources(response):
        found = []
        seen = set()

        def add(url, title=""):
            if isinstance(url, str) and url.startswith(("https://", "http://")) and url not in seen:
                seen.add(url)
                found.append({"url": url, "title": str(title or "").strip()})

        for block in response.get("content", []):
            if block.get("type") == "web_search_tool_result":
                for item in block.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "web_search_result":
                        add(item.get("url"), item.get("title"))
            if block.get("type") == "text":
                for citation in block.get("citations", []):
                    if isinstance(citation, dict):
                        add(citation.get("url"), citation.get("title"))
        return found

    def discover(self, conference, year, limit=5, award_types=None):
        if not 1 <= limit <= 10:
            raise ValueError("候选网址数量应在 1–10 之间")
        selected = set(award_types or ("best_paper", "best_student_paper"))
        if not selected or not selected.issubset({"best_paper", "best_student_paper"}):
            raise ValueError("请选择最佳论文奖或最佳学生论文奖")
        targets = [label for key, label in (("best_paper", "Best Paper Award"),
                                            ("best_student_paper", "Best Student Paper Award")) if key in selected]
        prompt = (f"Search the web for official {conference['full_name']} ({conference['acronym']}) "
                  f"{year} {' or '.join(targets)} winner announcements. "
                  "Use the web_search tool. Prefer the conference or publisher website. "
                  "Return the strongest official pages with citations; do not invent URLs.")
        response = self._post({
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
        })
        self.last_usage = normalize_usage(response, self.provider, self.model)
        if response.get("type") != "message" or response.get("stop_reason") == "max_tokens":
            raise ValueError("DeepSeek 网页搜索响应未完整结束")
        if not any(isinstance(block, dict) and block.get("type") == "server_tool_use" and
                   block.get("name") == "web_search" for block in response.get("content", [])):
            raise ValueError("DeepSeek 未实际调用网页搜索工具；此次请求可能已产生 Token 费用")
        candidates = self._sources(response)
        if not candidates:
            raise ValueError("DeepSeek 没有返回可核验的网页搜索结果；此次请求可能已产生 Token 费用")
        return {
            "conference_id": conference["id"],
            "conference": conference["acronym"],
            "year": year,
            "model": self.model,
            "candidates": candidates[:limit],
            "token_usage": self.last_usage,
        }


class ZhipuWebSearch(ResponsesWebSearch):
    """Use Zhipu's server-side Chat Completions web_search tool."""

    def __init__(self, api_key, base_url, model):
        super().__init__(api_key=api_key, base_url=base_url, model=model, provider="zhipu")
        if urlsplit(self.base).hostname not in ("open.bigmodel.cn", "api.z.ai"):
            raise ValueError("智谱网页搜索仅支持官方 API 地址")

    def _post(self, body):
        request = urllib.request.Request(
            self.base + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=120) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("网页搜索 API 响应超过 8 MiB")
            return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"智谱网页搜索 HTTP {exc.code}；当前模型可能不支持 web_search 工具") from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("智谱网页搜索网络失败或超时") from None
        except json.JSONDecodeError:
            raise ValueError("智谱网页搜索返回了无效 JSON") from None

    def discover(self, conference, year, limit=5, award_types=None):
        if not 1 <= limit <= 10:
            raise ValueError("候选网址数量应在 1–10 之间")
        selected = set(award_types or ("best_paper", "best_student_paper"))
        if not selected or not selected.issubset({"best_paper", "best_student_paper"}):
            raise ValueError("请选择最佳论文奖或最佳学生论文奖")
        targets = [label for key, label in (("best_paper", "Best Paper Award"),
                                            ("best_student_paper", "Best Student Paper Award")) if key in selected]
        prompt = (f"Find official {conference['full_name']} ({conference['acronym']}) {year} "
                  f"{' or '.join(targets)} winner announcements. Return official URLs.")
        response = self._post({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [{"type": "web_search", "web_search": {"search_query": prompt, "search_result": True}}],
            "stream": False,
        })
        self.last_usage = normalize_usage(response, self.provider, self.model)
        choices = response.get("choices") or []
        message = choices[0].get("message") or {} if choices else {}
        found = []
        seen = set()
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            results = call.get("search_result")
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except json.JSONDecodeError:
                    results = []
            for item in results if isinstance(results, list) else []:
                if not isinstance(item, dict):
                    continue
                url = item.get("link") or item.get("url")
                if isinstance(url, str) and url.startswith(("https://", "http://")) and url not in seen:
                    seen.add(url)
                    found.append({"url": url, "title": str(item.get("title") or "").strip()})
        if not found:
            raise ValueError("智谱模型未返回可核验的 web_search 来源；请换支持搜索的模型或使用已有网址")
        return {
            "conference_id": conference["id"], "conference": conference["acronym"],
            "year": year, "model": self.model, "candidates": found[:limit],
            "token_usage": self.last_usage,
        }


# Backward-compatible name for code written before search/extraction were separated.
OpenAIWebSearch = ResponsesWebSearch
