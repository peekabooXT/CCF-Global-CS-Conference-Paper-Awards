"""Normalize token usage returned by supported API styles."""


def _token(value):
    return value if isinstance(value, int) and value >= 0 else None


def normalize_usage(response, provider=None, model=None):
    if not isinstance(response, dict) or not isinstance(response.get("usage"), dict):
        return None
    usage = response["usage"]
    input_tokens = _token(usage.get("input_tokens"))
    if input_tokens is None:
        input_tokens = _token(usage.get("prompt_tokens"))
    output_tokens = _token(usage.get("output_tokens"))
    if output_tokens is None:
        output_tokens = _token(usage.get("completion_tokens"))
    total_tokens = _token(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    result = {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}
    if provider:
        result["provider"] = provider
    if model:
        result["model"] = model
    input_details = usage.get("input_tokens_details") or usage.get("prompt_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or usage.get("completion_tokens_details") or {}
    optional = {
        "cached_input_tokens": _token(input_details.get("cached_tokens")),
        "reasoning_output_tokens": _token(output_details.get("reasoning_tokens")),
        "cache_hit_input_tokens": _token(usage.get("prompt_cache_hit_tokens")),
        "cache_miss_input_tokens": _token(usage.get("prompt_cache_miss_tokens")),
    }
    result.update({key: value for key, value in optional.items() if value is not None})
    return result
