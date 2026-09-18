"""Official-page discovery through a Responses API with a real web_search tool."""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .model import url_syntax
from .network import NoRedirect


class ResponsesWebSearch:
    """Find candidate official award pages; fetching and validation happen later."""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.key = api_key if api_key is not None else os.getenv("SEARCH_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.base = (base_url if base_url is not None else os.getenv("SEARCH_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))).rstrip("/")
        self.model = model if model is not None else os.getenv("SEARCH_MODEL", os.getenv("OPENAI_SEARCH_MODEL", ""))
        if not self.key or not self.model:
            raise ValueError("自主搜索需要 SEARCH_API_KEY 和 SEARCH_MODEL（OpenAI 可直接使用 OPENAI_API_KEY/OPENAI_SEARCH_MODEL）")
        url_syntax(self.base)
        if urlsplit(self.base).scheme != "https":
            raise ValueError("SEARCH_BASE_URL 必须使用 HTTPS")

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

    def discover(self, conference, year, limit=5):
        if not 1 <= limit <= 10:
            raise ValueError("候选网址数量应在 1–10 之间")
        prompt = f"""Find official web pages for {conference['full_name']} ({conference['acronym']}) {year}
that explicitly announce Best Paper Award or Best Student Paper Award winners.
Prioritize the conference website and the official publisher/society website.
Do not use social media, scraped award aggregators, or search-result snippets as evidence.
Search for both award types and return a short answer with the strongest official pages."""
        response = self._post({
            "model": self.model,
            "instructions": "Use web search to locate official sources only. Candidate URLs will be fetched and independently validated by another component.",
            "input": prompt,
            "tools": [{"type": "web_search"}],
            "tool_choice": "required",
            "include": ["web_search_call.action.sources"],
            "max_tool_calls": 3,
            "store": False,
        })
        if response.get("status") not in (None, "completed"):
            raise ValueError("网页搜索响应未完整结束")
        return {
            "conference_id": conference["id"],
            "conference": conference["acronym"],
            "year": year,
            "model": self.model,
            "candidates": self._sources(response)[:limit],
        }


# Backward-compatible name for code written before search/extraction were separated.
OpenAIWebSearch = ResponsesWebSearch
