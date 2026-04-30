"""Financial-filing retrieval tool backed by the extension KB."""

from __future__ import annotations

from typing import Any

from tools.company_entity_router import (
    DEFAULT_LLM_ROUTER_MAX_TICKERS,
    company_display_name,
    resolve_target_tickers,
)
from tools.kb_pipeline_provider import get_kb_pipeline


DEFAULT_CHUNK_ROLES = ["evidence"]
DEFAULT_MULTI_COMPANY_RESULTS_PER_TICKER = 3
DEFAULT_LLM_ROUTER_RESULTS_PER_TICKER = 1
DEFAULT_MAX_CONTENT_CHARS = 3500


def retrieve_filings(query: str, n_results: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Retrieve financial-filing evidence chunks from the Qdrant-backed KB.

    Args:
        query: User query text.
        n_results: Number of evidence hits to return.
        filters: Optional metadata filters. Supported keys include:
            ticker, period_end, report_type, statement_type, chunk_roles, expand_neighbors,
            max_content_chars.
    """

    filters = filters or {}
    explicit_tickers = _normalize_sequence(filters.get("ticker") or filters.get("tickers"))
    period_end = _clean_optional_string(filters.get("period_end") or filters.get("period"))
    report_type = _clean_optional_string(filters.get("report_type"))
    statement_type = _clean_optional_string(filters.get("statement_type"))
    chunk_roles = _normalize_sequence(filters.get("chunk_roles") or filters.get("chunk_role")) or DEFAULT_CHUNK_ROLES
    expand_neighbors = _normalize_bool(filters.get("expand_neighbors"), default=False)
    max_content_chars = _normalize_positive_int(
        filters.get("max_content_chars"),
        default=DEFAULT_MAX_CONTENT_CHARS,
    )
    enable_entity_router = _normalize_bool(filters.get("enable_entity_router"), default=True)
    max_router_tickers = max(
        1,
        _normalize_int(
            filters.get("max_router_tickers"),
            default=min(max(n_results, 1), DEFAULT_LLM_ROUTER_MAX_TICKERS),
        ),
    )
    target_tickers, detection_source = resolve_target_tickers(
        query=query,
        explicit_tickers=explicit_tickers or None,
        enable_entity_router=enable_entity_router and not explicit_tickers,
        max_tickers=max_router_tickers,
    )
    default_per_ticker = (
        DEFAULT_LLM_ROUTER_RESULTS_PER_TICKER
        if detection_source == "llm_entity_router"
        else min(max(n_results, 1), DEFAULT_MULTI_COMPANY_RESULTS_PER_TICKER)
    )
    per_ticker_results = max(
        1,
        _normalize_int(filters.get("per_ticker_results"), default=default_per_ticker),
    )

    pipeline = get_kb_pipeline()
    if not target_tickers:
        hits = pipeline.search(
            query=query,
            top_k=n_results,
            doc_types=["filing"],
            ticker=None,
            chunk_roles=chunk_roles,
            period_end=period_end,
            report_type=report_type,
            statement_type=statement_type,
            expand_neighbors=expand_neighbors,
        )
        return [_format_hit(hit, retrieval_mode="raw_query", max_content_chars=max_content_chars) for hit in hits]

    if len(target_tickers) == 1:
        ticker = target_tickers[0]
        hits = pipeline.search(
            query=query,
            top_k=n_results,
            doc_types=["filing"],
            ticker=ticker,
            chunk_roles=chunk_roles,
            period_end=period_end,
            report_type=report_type,
            statement_type=statement_type,
            expand_neighbors=expand_neighbors,
        )
        if not hits:
            return [_empty_ticker_result(query=query, ticker=ticker, detection_source=detection_source)]
        return [
            _format_hit(
                hit,
                retrieval_mode="ticker_filter",
                max_content_chars=max_content_chars,
                matched_ticker=ticker,
                detected_tickers=target_tickers,
                detection_source=detection_source,
            )
            for hit in hits
        ]

    results: list[dict[str, Any]] = []
    for ticker in target_tickers:
        hits = pipeline.search(
            query=query,
            top_k=per_ticker_results,
            doc_types=["filing"],
            ticker=ticker,
            chunk_roles=chunk_roles,
            period_end=period_end,
            report_type=report_type,
            statement_type=statement_type,
            expand_neighbors=expand_neighbors,
        )
        if not hits:
            results.append(
                _empty_ticker_result(
                    query=query,
                    ticker=ticker,
                    detection_source=detection_source,
                    retrieval_mode="multi_ticker_filter",
                    detected_tickers=target_tickers,
                )
            )
            continue
        results.extend(
            _format_hit(
                hit,
                retrieval_mode="multi_ticker_filter",
                max_content_chars=max_content_chars,
                matched_ticker=ticker,
                detected_tickers=target_tickers,
                detection_source=detection_source,
            )
            for hit in hits
        )
    return results


def _format_hit(
    hit,
    retrieval_mode: str,
    max_content_chars: int | None,
    matched_ticker: str | None = None,
    detected_tickers: list[str] | None = None,
    detection_source: str | None = None,
) -> dict[str, Any]:
    metadata = dict(hit.payload)
    metadata["retrieval_mode"] = retrieval_mode
    if matched_ticker:
        metadata["matched_ticker_filter"] = matched_ticker
    if detected_tickers:
        metadata["detected_tickers"] = detected_tickers
    if detection_source:
        metadata["ticker_detection_source"] = detection_source
    content, was_truncated = _truncate_content(hit.content, max_content_chars)
    metadata["retrieval_status"] = "ok"
    metadata["content_truncated"] = was_truncated
    metadata["original_content_chars"] = len(hit.content)
    metadata["returned_content_chars"] = len(content)
    if max_content_chars is not None:
        metadata["max_content_chars"] = max_content_chars
    return {
        "content": content,
        "metadata": metadata,
        "score": hit.score,
    }


def _empty_ticker_result(
    query: str,
    ticker: str,
    detection_source: str,
    retrieval_mode: str = "ticker_filter",
    detected_tickers: list[str] | None = None,
) -> dict[str, Any]:
    name = company_display_name(ticker)
    detected_tickers = detected_tickers or [ticker]
    return {
        "content": f"本地财报/公告库未检索到 {ticker}（{name}）的相关证据。原始问题：{query}",
        "metadata": {
            "ticker": ticker,
            "source_title": name,
            "retrieval_mode": retrieval_mode,
            "matched_ticker_filter": ticker,
            "detected_tickers": detected_tickers,
            "retrieval_status": "no_hits",
            "ticker_detection_source": detection_source,
        },
        "score": 0.0,
    }


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_positive_int(value: Any, default: int) -> int | None:
    number = _normalize_int(value, default)
    return number if number > 0 else None


def _truncate_content(content: str, max_chars: int | None) -> tuple[str, bool]:
    content = str(content)
    if max_chars is None or len(content) <= max_chars:
        return content, False

    marker = f"\n\n[内容已截断，原始 {len(content)} 字符。可通过 filters.max_content_chars 调整上限。]"
    if len(marker) >= max_chars:
        return marker[:max_chars], True
    keep_chars = max(0, max_chars - len(marker))
    return content[:keep_chars].rstrip() + marker, True
