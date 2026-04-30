import os
from typing import Any, Dict, List, Union

import httpx

from utils.config import load_config


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_OPENROUTER_TIMEOUT_SECONDS = 60


def _messages_to_openai_format(messages: Union[str, List[Dict[str, str]]]) -> list[dict[str, str]]:
    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, list):
        return [
            {
                "role": str(message.get("role", "user")),
                "content": str(message.get("content", "")),
            }
            for message in messages
        ]
    raise TypeError("messages must be a string or a list of chat messages")


def openrouter_chat(
    messages: Union[str, List[Dict[str, str]]],
    timeout: int | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Call OpenRouter's OpenAI-compatible chat completion API."""
    config = load_config()
    openrouter_config = config.get("openrouter", {})
    api_key = openrouter_config.get("api_key") or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "错误: 未配置 OpenRouter API Key。请设置 OPENROUTER_API_KEY 或 config.local.yml 的 openrouter.api_key。"

    model = (
        model_name
        or os.environ.get("OPENROUTER_MODEL")
        or openrouter_config.get("model")
        or DEFAULT_OPENROUTER_MODEL
    )
    resolved_base_url = (
        base_url
        or os.environ.get("OPENROUTER_BASE_URL")
        or openrouter_config.get("base_url")
        or DEFAULT_OPENROUTER_BASE_URL
    ).rstrip("/")
    timeout_seconds = int(
        timeout
        or os.environ.get("OPENROUTER_TIMEOUT_SECONDS")
        or openrouter_config.get("timeout_seconds")
        or DEFAULT_OPENROUTER_TIMEOUT_SECONDS
    )

    payload: dict[str, Any] = {
        "model": model,
        "messages": _messages_to_openai_format(messages),
    }
    if options:
        for key, value in options.items():
            if key in {"temperature", "top_p", "max_tokens", "stop", "seed"}:
                payload[key] = value

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": openrouter_config.get("referer", "https://github.com/Jacob-Qiu/FinAgent"),
        "X-Title": openrouter_config.get("title", "FinAgent"),
    }

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                f"{resolved_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return str(data["choices"][0]["message"]["content"])
    except Exception as e:
        return f"OpenRouter API 调用失败: {str(e)}"
