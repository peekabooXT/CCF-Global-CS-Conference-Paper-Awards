"""Named LLM provider profiles; explicit environment values always win."""

PROVIDER_PROFILES = {
    "deepseek": {
        "label": "DeepSeek（默认）",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "",
        "key_env": "OPENAI_API_KEY",
    },
    "custom": {
        "label": "OpenAI Chat Completions 兼容/自定义",
        "base_url": "",
        "model": "",
        "key_env": "LLM_API_KEY",
    },
}


def provider_profile(name):
    provider = str(name or "deepseek").strip().lower()
    aliases = {"deepseek-ai": "deepseek", "open-ai": "openai", "compatible": "custom"}
    provider = aliases.get(provider, provider)
    if provider not in PROVIDER_PROFILES:
        raise ValueError("LLM_PROVIDER 仅支持 deepseek、openai 或 custom")
    return provider, PROVIDER_PROFILES[provider]
