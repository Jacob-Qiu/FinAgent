"""
AkShare-based hot news aggregation helpers.

This module collects broad market hot news from the AkShare interfaces that are
available in the current environment and normalizes them into a raw MCP-style
payload. The payload is intentionally kept lightweight so the existing cleaning
pipeline can turn it into a concise briefing for the agent.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta
from typing import Any

import akshare as ak


DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        text = " ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value).strip()
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shorten_text(text: str, max_chars: int = 220) -> str:
    clean = _clean_text(text)
    if not clean:
        return ""
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip("，,；;：: ") + "…"


def _normalize_date(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    candidates = (
        "%Y-%m-%d",
        "%Y%m%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    )
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text[: len(fmt.replace("%f", "000000"))], fmt)
            return parsed.strftime("%Y-%m-%d")
        except Exception:
            continue

    match = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return text[:10]


def _extract_date_from_url(url: str) -> str:
    match = re.search(r"/(\d{4}-\d{2}-\d{2})/", url)
    return match.group(1) if match else ""


def _normalize_item(
    *,
    title: str,
    summary: str,
    source: str,
    publish_date: str,
    url: str,
    tag: str = "",
) -> dict[str, Any]:
    title = _clean_text(title)
    summary = _clean_text(summary)
    source = _clean_text(source) or "AkShare"
    publish_date = _normalize_date(publish_date)
    url = _clean_text(url)
    tag = _clean_text(tag)

    if not title:
        title = summary[:48] if summary else tag or source
    if not summary:
        summary = title

    digest_seed = "|".join([publish_date, source, title, summary, url, tag])
    return {
        "id": hashlib.md5(digest_seed.encode("utf-8")).hexdigest(),
        "publishDate": publish_date,
        "source": source,
        "title": title,
        "summary": _shorten_text(summary, 240),
        "url": url,
        "tag": tag,
    }


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (
            _normalize_date(item.get("publishDate")),
            _clean_text(item.get("source")).lower(),
            re.sub(r"[\s\W_]+", "", f"{item.get('title', '')} {item.get('summary', '')}".lower()),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _maybe_call_akshare(name: str, *args: Any, **kwargs: Any):
    fn = getattr(ak, name, None)
    if not callable(fn):
        return None
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _fetch_cls_news_items(limit: int) -> list[dict[str, Any]]:
    df = _maybe_call_akshare("cls_news", category="")
    if df is None or getattr(df, "empty", True):
        return []

    items: list[dict[str, Any]] = []
    for row in df.head(limit).to_dict(orient="records"):
        title = _clean_text(row.get("标题") or row.get("title") or row.get("headline") or "")
        summary = _clean_text(row.get("内容") or row.get("content") or row.get("summary") or "")
        publish_date = _normalize_date(row.get("发布时间") or row.get("date") or row.get("time") or "")
        items.append(
            _normalize_item(
                title=title,
                summary=summary,
                source="财联社",
                publish_date=publish_date,
                url=_clean_text(row.get("url") or row.get("link") or ""),
                tag="cls_news",
            )
        )
    return items


def _fetch_js_news_items(limit: int) -> list[dict[str, Any]]:
    df = _maybe_call_akshare("js_news", category="主要")
    if df is None or getattr(df, "empty", True):
        return []

    items: list[dict[str, Any]] = []
    for row in df.head(limit).to_dict(orient="records"):
        title = _clean_text(row.get("标题") or row.get("title") or row.get("headline") or row.get("content") or "")
        summary = _clean_text(row.get("内容") or row.get("content") or row.get("summary") or "")
        publish_date = _normalize_date(row.get("时间") or row.get("datetime") or row.get("date") or row.get("time") or "")
        items.append(
            _normalize_item(
                title=title,
                summary=summary,
                source="金十数据",
                publish_date=publish_date,
                url=_clean_text(row.get("url") or row.get("link") or ""),
                tag="js_news",
            )
        )
    return items


def _fetch_stock_news_main_cx_items(limit: int) -> list[dict[str, Any]]:
    df = _maybe_call_akshare("stock_news_main_cx")
    if df is None or getattr(df, "empty", True):
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    items: list[dict[str, Any]] = []
    for row in df.head(limit).to_dict(orient="records"):
        tag = _clean_text(row.get("tag") or "")
        summary = _clean_text(row.get("summary") or "")
        url = _clean_text(row.get("url") or "")
        publish_date = _extract_date_from_url(url) or today
        items.append(
            _normalize_item(
                title=summary,
                summary=summary,
                source="财新" if not tag else f"财新-{tag}",
                publish_date=publish_date,
                url=url,
                tag=tag or "stock_news_main_cx",
            )
        )
    return items


def _fetch_news_cctv_items(limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for delta in range(0, 2):
        date = (datetime.now() - timedelta(days=delta)).strftime("%Y%m%d")
        df = _maybe_call_akshare("news_cctv", date=date)
        if df is None or getattr(df, "empty", True):
            continue
        for row in df.head(limit).to_dict(orient="records"):
            title = _clean_text(row.get("title") or row.get("标题") or "")
            content = _clean_text(row.get("content") or row.get("内容") or row.get("summary") or "")
            publish_date = _normalize_date(row.get("date") or date)
            items.append(
                _normalize_item(
                    title=title,
                    summary=content,
                    source="央视新闻",
                    publish_date=publish_date,
                    url="",
                    tag="news_cctv",
                )
            )
        if items:
            break
    return items


def fetch_hot_news_raw(limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """
    Collect a broad market hot-news batch from AkShare sources.

    The return shape mirrors the MCP-style payload used elsewhere in the app so
    the existing briefing pipeline can consume it without additional adapters.
    """

    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))

    source_limit = max(limit, 20)
    items: list[dict[str, Any]] = []

    for batch in (
        _fetch_cls_news_items(source_limit),
        _fetch_js_news_items(source_limit),
        _fetch_stock_news_main_cx_items(source_limit),
        _fetch_news_cctv_items(source_limit),
    ):
        items.extend(batch)

    items = _dedupe_items(items)
    items.sort(key=lambda item: (item.get("publishDate") or "", item.get("source") or "", item.get("id") or ""), reverse=True)
    items = items[:limit]

    return {
        "success": bool(items),
        "data": {
            "total": len(items),
            "page": 1,
            "pageSize": limit,
            "totalPages": 1 if items else 0,
            "items": items,
        },
    }
