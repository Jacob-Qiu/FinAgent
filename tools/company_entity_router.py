"""Shared company-entity routing for KB retrieval tools."""

from __future__ import annotations

from functools import lru_cache
import json
import re
from typing import Any

from data_pipeline.settings import REPO_ROOT, load_extension_settings
from utils.config import load_config
import yaml


DEFAULT_LLM_ROUTER_MAX_TICKERS = 8
LLM_ROUTER_TIMEOUT_SECONDS = 120


def resolve_target_tickers(
    query: str,
    explicit_tickers: list[str] | None = None,
    enable_entity_router: bool = True,
    max_tickers: int = DEFAULT_LLM_ROUTER_MAX_TICKERS,
) -> tuple[list[str], str]:
    """Resolve target tickers from explicit filters, aliases, then LLM router."""

    if explicit_tickers:
        tickers = [canonical_ticker(item) for item in explicit_tickers if canonical_ticker(item)]
        return _deduplicate_tickers(tickers), "explicit_filter"

    tickers = detect_tickers_from_query(query)
    if tickers:
        return tickers, "company_aliases"

    if enable_entity_router:
        routed = route_tickers_with_llm(query, max_tickers=max_tickers)
        if routed:
            return routed, "llm_entity_router"

    return [], "raw_query"


def detect_tickers_from_query(query: str) -> list[str]:
    text = str(query or "")
    if not text.strip():
        return []

    matches: dict[str, int] = {}
    for ticker, entry in company_alias_map().items():
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list):
            continue
        positions = [
            position
            for alias in aliases
            if (position := _alias_match_position(text, str(alias))) is not None
        ]
        if positions:
            matches[ticker] = min(positions)

    return [ticker for ticker, _ in sorted(matches.items(), key=lambda item: (item[1], item[0]))]


def route_tickers_with_llm(query: str, max_tickers: int) -> list[str]:
    prompt = build_entity_router_prompt(query=query, max_tickers=max_tickers)
    messages = [
        {
            "role": "system",
            "content": "你是 FinAgent 的检索对象路由器。你只负责从给定股票池里选择需要检索的 ticker，不回答投资问题。",
        },
        {"role": "user", "content": prompt},
    ]
    try:
        config = load_config()
        provider = str(config.get("llm_provider", "ollama")).strip().lower()
        if provider == "gemini":
            from llm.gemini_client import gemini_chat

            raw_response = gemini_chat(
                messages,
                timeout=LLM_ROUTER_TIMEOUT_SECONDS,
                options={"temperature": 0},
            )
        elif provider == "openrouter":
            from llm.openrouter_client import openrouter_chat

            raw_response = openrouter_chat(
                messages,
                timeout=LLM_ROUTER_TIMEOUT_SECONDS,
                options={"temperature": 0},
            )
        else:
            settings = load_extension_settings()
            from llm.ollama_client import ollama_chat

            raw_response = ollama_chat(
                messages,
                timeout=LLM_ROUTER_TIMEOUT_SECONDS,
                model_name=settings.llm.ollama_model,
                base_url=settings.llm.ollama_base_url,
                options={"temperature": 0},
            )
    except Exception:
        return []

    parsed = parse_router_json(raw_response)
    if not parsed:
        return []

    selected = parsed.get("selected_tickers")
    if not isinstance(selected, list):
        return []

    alias_map = company_alias_map()
    tickers: list[str] = []
    for item in selected:
        ticker = canonical_ticker(item)
        if ticker in alias_map and ticker not in tickers:
            tickers.append(ticker)
        if len(tickers) >= max_tickers:
            break
    return tickers


def build_entity_router_prompt(query: str, max_tickers: int) -> str:
    candidates = []
    for ticker, entry in company_alias_map().items():
        aliases = entry.get("aliases") or []
        candidates.append(
            {
                "ticker": ticker,
                "market": entry.get("market"),
                "name": entry.get("name"),
                "theme": entry.get("theme"),
                "aliases": aliases[:6] if isinstance(aliases, list) else [],
            }
        )

    return f"""请根据用户问题，从候选股票池中选择需要检索的 ticker。

严格约束：
1. 你的任务不是回答投资问题，只能选择检索对象。
2. 只能从候选股票池里选择 ticker，禁止编造池外 ticker。
3. 如果用户明确提到公司，选择对应 ticker。
4. 如果用户提到行业、主题或风格，选择最相关的 3-{max_tickers} 个 ticker。
5. 如果无法判断，selected_tickers 返回空数组。
6. 必须输出纯 JSON 对象，不要 Markdown，不要解释性文本。

输出 JSON 结构：
{{
  "intent": "single_company | multi_company_compare | theme_stock_selection | unknown",
  "selected_tickers": ["ticker1", "ticker2"],
  "confidence": 0.0,
  "reason": "简短说明"
}}

用户问题：
{query}

候选股票池：
{json.dumps(candidates, ensure_ascii=False)}
"""


def parse_router_json(raw_response: Any) -> dict[str, Any] | None:
    text = str(raw_response or "").strip()
    if not text:
        return None

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s*```$", "", text).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


def canonical_ticker(value: Any) -> str:
    ticker = str(value or "").strip()
    if not ticker:
        return ""
    alias_map = company_alias_map()
    if ticker in alias_map:
        return ticker
    upper_ticker = ticker.upper()
    if upper_ticker in alias_map:
        return upper_ticker
    ashare_match = re.fullmatch(r"(\d{6})\.(?:SZ|SH)", upper_ticker)
    if ashare_match:
        base_ticker = ashare_match.group(1)
        if base_ticker in alias_map:
            return base_ticker
    for symbol, entry in alias_map.items():
        aliases = entry.get("aliases") or []
        if any(str(alias).strip().lower() == ticker.lower() for alias in aliases):
            return symbol
    return upper_ticker


@lru_cache(maxsize=1)
def company_alias_map() -> dict[str, dict[str, Any]]:
    path = REPO_ROOT / "kb" / "company_aliases.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for ticker, entry in data.items():
        symbol = str(ticker).strip()
        if not symbol or not isinstance(entry, dict):
            continue
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = [aliases]
        cleaned_aliases = []
        for alias in aliases:
            alias_text = str(alias).strip()
            if alias_text and alias_text not in cleaned_aliases:
                cleaned_aliases.append(alias_text)
        if symbol not in cleaned_aliases:
            cleaned_aliases.insert(0, symbol)
        normalized[symbol] = {
            "market": entry.get("market"),
            "name": entry.get("name"),
            "theme": entry.get("theme"),
            "aliases": sorted(cleaned_aliases, key=len, reverse=True),
        }
    return normalized


def company_display_name(ticker: str) -> str:
    company = company_alias_map().get(ticker, {})
    return str(company.get("name") or ticker)


def _alias_match_position(text: str, alias: str) -> int | None:
    alias = alias.strip()
    if not alias:
        return None

    if _contains_cjk(alias):
        index = text.find(alias)
        return index if index >= 0 else None

    pattern = rf"(?<![A-Za-z0-9.]){re.escape(alias)}(?![A-Za-z0-9.])"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.start() if match else None


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _deduplicate_tickers(tickers: list[str]) -> list[str]:
    deduplicated: list[str] = []
    for ticker in tickers:
        if ticker and ticker not in deduplicated:
            deduplicated.append(ticker)
    return deduplicated
