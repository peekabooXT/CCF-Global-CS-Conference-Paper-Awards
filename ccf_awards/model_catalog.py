"""Fetch account-visible model IDs from known providers without exposing keys."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .network import NoRedirect
from .providers import provider_profile


def _catalog_url(provider, base_url):
    provider, profile = provider_profile(provider)
    if provider == "custom":
        raise ValueError("自定义服务请手动填写模型 ID")
    base = (base_url or profile["base_url"]).rstrip("/")
    parts = urlsplit(base)
    host = (parts.hostname or "").lower()
    allowed = {
        "deepseek": host == "api.deepseek.com",
        "openai": host == "api.openai.com",
        "bailian": host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com",
                            "dashscope-us.aliyuncs.com"} or host.endswith(".maas.aliyuncs.com"),
        "qwen": host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com",
                         "dashscope-us.aliyuncs.com"} or host.endswith(".maas.aliyuncs.com"),
        "zhipu": host in {"open.bigmodel.cn", "api.z.ai"},
    }
    if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or parts.password or \
            parts.query or parts.fragment or not allowed[provider]:
        raise ValueError("模型列表只允许访问所选提供商的官方 HTTPS 地址；自定义地址请手动填模型")
    if provider in ("bailian", "qwen"):
        if not parts.path.endswith("/compatible-mode/v1"):
            raise ValueError("百炼模型列表要求 API 地址以 /compatible-mode/v1 结尾")
        prefix = base[:-len("/compatible-mode/v1")]
        query = "?capabilities=TG&features=web-search&page_no=1&page_size=100"
        if provider == "qwen":
            query += "&providers=qwen"
        return prefix + "/api/v1/models" + query
    if provider == "zhipu" and not parts.path.endswith("/api/paas/v4"):
        raise ValueError("智谱 API 地址应以 /api/paas/v4 结尾")
    if provider == "openai" and parts.path != "/v1":
        raise ValueError("OpenAI API 地址应为 https://api.openai.com/v1")
    if provider == "deepseek" and parts.path not in ("", "/v1"):
        raise ValueError("DeepSeek API 地址应为 https://api.deepseek.com")
    return base + "/models"


def list_provider_models(provider, api_key, base_url=None):
    if not api_key or not api_key.strip():
        raise ValueError("请先填写当前提供商的 API Key 再刷新模型列表")
    provider, _ = provider_profile(provider)
    url = _catalog_url(provider, base_url)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + api_key.strip()})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("模型列表响应超过 2 MiB")
        payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"提供商模型列表 HTTP {exc.code}；请检查 Key、区域或 API 地址") from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("获取模型列表网络失败或超时") from None
    except json.JSONDecodeError:
        raise ValueError("提供商模型列表返回了无效 JSON") from None
    if provider in ("bailian", "qwen"):
        rows = (payload.get("output") or {}).get("models") or []
        models = [{"id": row["model"], "name": row.get("name") or row["model"]}
                  for row in rows if isinstance(row, dict) and isinstance(row.get("model"), str)]
    else:
        rows = payload.get("data") or []
        models = [{"id": row["id"], "name": row.get("name") or row["id"]}
                  for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]
    if not models:
        raise ValueError("该提供商没有返回可选模型；仍可手动填写模型 ID")
    return models
