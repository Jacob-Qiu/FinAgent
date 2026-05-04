"""Research-report retrieval tool backed by the extension KB."""

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


def retrieve_reports(query: str, n_results: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Retrieve research-report evidence chunks from the Qdrant-backed KB.

    Args:
        query: User query text.
        n_results: Number of evidence hits to return.
        filters: Optional metadata filters. Supported keys include:
            ticker, tickers, doc_types, chunk_roles, expand_neighbors,
            per_ticker_results, enable_entity_router, max_router_tickers.
    """

    filters = filters or {}
    explicit_tickers = _normalize_sequence(filters.get("ticker") or filters.get("tickers"))
    doc_types = _normalize_sequence(filters.get("doc_types") or filters.get("doc_type")) or ["report"]
    chunk_roles = _normalize_sequence(filters.get("chunk_roles") or filters.get("chunk_role")) or DEFAULT_CHUNK_ROLES
    expand_neighbors = _normalize_bool(filters.get("expand_neighbors"), default=True)
    enable_entity_router = _normalize_bool(filters.get("enable_entity_router"), default=True)
    max_router_tickers = max(
        1,
        _normalize_int(
            filters.get("max_router_tickers"),
            default=min(max(n_results, 1), DEFAULT_LLM_ROUTER_MAX_TICKERS),
        ),
    )

    if explicit_tickers:
        target_tickers, detection_source = resolve_target_tickers(
            query=query,
            explicit_tickers=explicit_tickers,
            enable_entity_router=False,
            max_tickers=max_router_tickers,
        )
    else:
        target_tickers, detection_source = resolve_target_tickers(
            query=query,
            enable_entity_router=enable_entity_router,
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
            doc_types=doc_types,
            ticker=None,
            chunk_roles=chunk_roles,
            expand_neighbors=expand_neighbors,
        )
        return [_format_hit(hit, retrieval_mode="raw_query") for hit in hits]

    if len(target_tickers) == 1:
        ticker = target_tickers[0]
        hits = pipeline.search(
            query=query,
            top_k=n_results,
            doc_types=doc_types,
            ticker=ticker,
            chunk_roles=chunk_roles,
            expand_neighbors=expand_neighbors,
        )
        if not hits:
            return [_empty_ticker_result(query=query, ticker=ticker, detection_source=detection_source)]
        return [
            _format_hit(
                hit,
                retrieval_mode="ticker_filter",
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
            doc_types=doc_types,
            ticker=ticker,
            chunk_roles=chunk_roles,
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
    return {
        "content": hit.content,
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
        "content": f"本地研报库未检索到 {ticker}（{name}）的相关研报证据。原始问题：{query}",
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
