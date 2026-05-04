"""7x24 hot-news tool backed by AkShare and local briefing cleanup."""

from __future__ import annotations

from tools.hot_news_feed import MAX_LIMIT, fetch_hot_news_raw
from tools.news_briefing import summarize_hot_news_for_agent


DEFAULT_LIMIT = 10


def _normalize_limit(value: int | None) -> int:
    try:
        number = int(value) if value is not None else DEFAULT_LIMIT
    except (TypeError, ValueError):
        number = DEFAULT_LIMIT
    return max(1, min(number, MAX_LIMIT))


def hot_news_7x24(limit: int = DEFAULT_LIMIT) -> str:
    """Return a cleaned 7x24 market-hot-news brief.

    The tool first pulls broad market news from AkShare, then runs the local
    clustering / dedup / sentiment / logic tagging briefing pipeline so the
    agent receives concise, prompt-ready output.
    """

    normalized_limit = _normalize_limit(limit)
    raw_result = fetch_hot_news_raw(limit=normalized_limit)
    return summarize_hot_news_for_agent(raw_result, limit=normalized_limit)
