"""
创建日期：2026年02月11日
介绍： Ollama下载的本地模型
"""

import requests

from utils.config import load_config




def ollama_chat(messages: list[dict], stream: bool = False, timeout: int = 600):
    config = load_config()
    ollama_base_url = config["ollama"]["base_url"]
    model_name = config["ollama"]["model"]
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
    }
    r = requests.post(ollama_base_url, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data["message"]["content"]
