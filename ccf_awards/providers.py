"""Named LLM provider profiles; explicit environment values always win."""

PROVIDER_PROFILES = {
    "deepseek": {
        "label": "DeepSeek（默认）",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5-mini",
        "key_env": "OPENAI_API_KEY",
    },
    "bailian": {
        "label": "阿里云百炼",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.8-max",
        "key_env": "DASHSCOPE_API_KEY",
    },
    "qwen": {
        "label": "阿里千问（百炼 API）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.8-max",
        "key_env": "DASHSCOPE_API_KEY",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.6",
        "key_env": "ZHIPUAI_API_KEY",
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
    aliases = {"deepseek-ai": "deepseek", "open-ai": "openai", "compatible": "custom",
               "dashscope": "bailian", "aliyun": "bailian", "glm": "zhipu"}
    provider = aliases.get(provider, provider)
    if provider not in PROVIDER_PROFILES:
        raise ValueError("LLM_PROVIDER 仅支持 deepseek、openai、bailian、qwen、zhipu 或 custom")
    return provider, PROVIDER_PROFILES[provider]
