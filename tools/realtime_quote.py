"""Realtime quote snapshot tool backed by AkShare."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from data_pipeline.settings import load_extension_settings
from data_pipeline.storage import read_parquet
from tools.akshare_search import akshare_search


FIELD_ALIASES = {
    "code": ("代码", "code", "symbol", "ticker"),
    "name": ("名称", "name", "股票简称", "证券简称"),
    "latest_price": ("最新价", "现价", "price", "last", "latest_price"),
    "price_change": ("涨跌额", "change", "price_change"),
    "pct_change": ("涨跌幅", "changepercent", "pct_change", "change_pct"),
    "open": ("今开", "开盘", "开盘价", "open"),
    "high": ("最高", "最高价", "high"),
    "low": ("最低", "最低价", "low"),
    "prev_close": ("昨收", "昨收价", "prev_close", "previous_close"),
    "volume": ("成交量", "volume"),
    "amount": ("成交额", "amount", "turnover"),
    "amplitude": ("振幅", "amplitude"),
    "turnover_rate": ("换手率", "turnover_rate"),
    "volume_ratio": ("量比", "volume_ratio"),
}


def realtime_quote(
    query: str,
    market_type: str | None = None,
    include_raw: bool = False,
) -> str:
    """Return a prompt-friendly realtime quote snapshot.

    Args:
        query: Stock code/name, e.g. 600036, NVDA, 0700.HK, 腾讯.
        market_type: Optional market hint: cn, us, hk.
        include_raw: Whether to append the normalized raw row.
    """

    prepared_query = _prepare_query_for_market(query, market_type)
    raw_result = akshare_search(prepared_query, data_type="realtime")
    snapshots = _extract_quote_snapshots(raw_result, query=query, market_type=market_type)
    if not snapshots:
        return "\n".join(
            [
                "### 实时行情快照",
                f"- 查询: {query}",
                "- 结果: AkShare 未返回可解析的实时行情行。",
            ]
        )

    rendered = [_render_quote_snapshot(snapshot, include_raw=include_raw) for snapshot in snapshots]
    return "\n\n".join(rendered)


def _prepare_query_for_market(query: str, market_type: str | None) -> str:
    text = str(query or "").strip()
    market = str(market_type or "").strip().lower()
    if not text or not market:
        return text

    upper = text.upper()
    if market == "us" and not upper.endswith(".US"):
        return f"{upper}.US"
    if market == "hk" and not upper.endswith(".HK"):
        return f"{upper}.HK"
    if market == "cn":
        return text.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    return text


def _extract_quote_snapshots(raw_result: Any, query: str, market_type: str | None) -> list[dict[str, Any]]:
    if isinstance(raw_result, dict):
        snapshots: list[dict[str, Any]] = []
        for key, value in raw_result.items():
            rows = _rows_from_result(value)
            if not rows:
                snapshots.append({"query": key, "error": str(value)})
                continue
            snapshots.extend(_build_snapshot(row, query=key, market_type=market_type) for row in rows)
        return snapshots

    rows = _rows_from_result(raw_result)
    return [_build_snapshot(row, query=query, market_type=market_type) for row in rows]


def _rows_from_result(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return [dict(row) for row in value.to_dict(orient="records")]
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [dict(value)]
    return []


def _build_snapshot(row: dict[str, Any], query: str, market_type: str | None) -> dict[str, Any]:
    code = _clean_text(_get_first(row, FIELD_ALIASES["code"]))
    name = _clean_text(_get_first(row, FIELD_ALIASES["name"]))
    inferred_market = _infer_market(code, market_type)
    storage_symbol = _storage_symbol(code=code, market=inferred_market, query=query)

    latest_price = _to_float(_get_first(row, FIELD_ALIASES["latest_price"]))
    volume = _to_float(_get_first(row, FIELD_ALIASES["volume"]))
    historical_context = _load_historical_context(
        market=inferred_market,
        storage_symbol=storage_symbol,
        latest_price=latest_price,
        realtime_volume=volume,
    )

    return {
        "query": query,
        "market": inferred_market or "UNKNOWN",
        "code": code or storage_symbol or query,
        "storage_symbol": storage_symbol,
        "name": name,
        "latest_price": latest_price,
        "price_change": _to_float(_get_first(row, FIELD_ALIASES["price_change"])),
        "pct_change": _to_float(_get_first(row, FIELD_ALIASES["pct_change"])),
        "open": _to_float(_get_first(row, FIELD_ALIASES["open"])),
        "high": _to_float(_get_first(row, FIELD_ALIASES["high"])),
        "low": _to_float(_get_first(row, FIELD_ALIASES["low"])),
        "prev_close": _to_float(_get_first(row, FIELD_ALIASES["prev_close"])),
        "volume": volume,
        "amount": _to_float(_get_first(row, FIELD_ALIASES["amount"])),
        "amplitude": _to_float(_get_first(row, FIELD_ALIASES["amplitude"])),
        "turnover_rate": _to_float(_get_first(row, FIELD_ALIASES["turnover_rate"])),
        "quote_volume_ratio": _to_float(_get_first(row, FIELD_ALIASES["volume_ratio"])),
        "historical_context": historical_context,
        "raw_row": row,
    }


def _render_quote_snapshot(snapshot: dict[str, Any], include_raw: bool) -> str:
    if snapshot.get("error"):
        return "\n".join(
            [
                "### 实时行情快照",
                f"- 查询: {snapshot.get('query')}",
                f"- 结果: {snapshot.get('error')}",
            ]
        )

    title_parts = [str(snapshot.get("name") or "").strip(), str(snapshot.get("storage_symbol") or snapshot.get("code") or "").strip()]
    title = " / ".join(part for part in title_parts if part) or str(snapshot.get("query") or "UNKNOWN")
    context = snapshot.get("historical_context") or {}

    lines = [
        f"### 【{title}】实时行情快照",
        f"- 数据源: AkShare realtime spot",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 市场: {snapshot.get('market')}",
        f"- 原始代码: {snapshot.get('code')}",
        "",
        "【实时价格】",
        f"- 最新价: {_fmt_number(snapshot.get('latest_price'))}",
        f"- 涨跌额: {_fmt_signed_number(snapshot.get('price_change'))}",
        f"- 涨跌幅: {_fmt_signed_percent(snapshot.get('pct_change'))}",
        f"- 今开/最高/最低/昨收: {_fmt_number(snapshot.get('open'))} / {_fmt_number(snapshot.get('high'))} / {_fmt_number(snapshot.get('low'))} / {_fmt_number(snapshot.get('prev_close'))}",
        "",
        "【成交与强度】",
        f"- 成交量: {_fmt_large(snapshot.get('volume'))}",
        f"- 成交额: {_fmt_money(snapshot.get('amount'))}",
        f"- 换手率: {_fmt_percent(snapshot.get('turnover_rate'))}",
        f"- 振幅: {_fmt_percent(snapshot.get('amplitude'))}",
        f"- AkShare量比: {_fmt_number(snapshot.get('quote_volume_ratio'))}",
    ]

    if context:
        lines.extend(
            [
                f"- 成交量异动比率: {_fmt_number(context.get('volume_anomaly_ratio'))}（当前累计成交量 / 近20日日均成交量）",
                f"- 近20日日均成交量: {_fmt_large(context.get('avg_volume_20'))}",
                f"- 本地历史样本日期: {context.get('last_history_date') or 'N/A'}",
                "",
                "【相对历史技术位】",
                f"- 相对MA20: {_fmt_signed_percent(context.get('vs_ma20_pct'))}",
                f"- 相对MA60: {_fmt_signed_percent(context.get('vs_ma60_pct'))}",
                f"- 最近日线RSI(14): {_fmt_number(context.get('rsi_14'))}",
                f"- 最近日线MACD柱: {_fmt_signed_number(context.get('macd_hist'))}",
            ]
        )

    lines.extend(
        [
            "",
            "【给下游模型的提示】",
            _build_prompt_hint(snapshot, context),
        ]
    )

    if include_raw:
        lines.extend(["", "【标准化原始行】", str(snapshot.get("raw_row") or {})])

    return "\n".join(lines)


def _build_prompt_hint(snapshot: dict[str, Any], context: dict[str, Any]) -> str:
    pct_change = snapshot.get("pct_change")
    volume_anomaly = context.get("volume_anomaly_ratio") if context else None

    hints: list[str] = []
    if isinstance(pct_change, (int, float)):
        if pct_change >= 3:
            hints.append("价格短线强势上涨")
        elif pct_change <= -3:
            hints.append("价格短线明显下跌")
        elif pct_change >= 1:
            hints.append("价格小幅走强")
        elif pct_change <= -1:
            hints.append("价格小幅走弱")
        else:
            hints.append("价格波动较温和")

    if isinstance(volume_anomaly, (int, float)):
        if volume_anomaly >= 2:
            hints.append("成交量相对近20日显著放大")
        elif volume_anomaly >= 1.2:
            hints.append("成交量相对近20日偏活跃")
        elif volume_anomaly <= 0.5:
            hints.append("成交量相对近20日偏低")
        else:
            hints.append("成交量接近近20日常态")

    if not hints:
        return "这是实时行情证据块。请优先使用最新价、涨跌幅、成交量和成交量异动比率判断当前市场强度。"
    return "；".join(hints) + "。"


def _load_historical_context(
    market: str | None,
    storage_symbol: str,
    latest_price: float | None,
    realtime_volume: float | None,
) -> dict[str, Any]:
    if not market or not storage_symbol:
        return {}

    settings = load_extension_settings()
    path = settings.storage.market_data_dir / market / "daily" / f"{storage_symbol}.parquet"
    if not path.exists():
        return {}

    try:
        frame = read_parquet(path)
    except Exception:
        return {}

    if frame.empty:
        return {}

    context: dict[str, Any] = {"history_path": str(path)}
    if "date" in frame.columns:
        last_date = pd.to_datetime(frame["date"], errors="coerce").dropna()
        if not last_date.empty:
            context["last_history_date"] = last_date.max().strftime("%Y-%m-%d")

    if "volume" in frame.columns:
        avg_volume_20 = pd.to_numeric(frame["volume"], errors="coerce").tail(20).mean()
        if avg_volume_20 and not pd.isna(avg_volume_20):
            context["avg_volume_20"] = float(avg_volume_20)
            if realtime_volume is not None:
                context["volume_anomaly_ratio"] = float(realtime_volume) / float(avg_volume_20)

    latest_row = frame.tail(1).iloc[0]
    for key in ("ma_20", "ma_60", "rsi_14", "macd_hist"):
        value = _to_float(latest_row.get(key))
        if value is not None:
            context[key] = value

    if latest_price is not None:
        ma20 = context.get("ma_20")
        ma60 = context.get("ma_60")
        if ma20:
            context["vs_ma20_pct"] = (latest_price / ma20 - 1.0) * 100.0
        if ma60:
            context["vs_ma60_pct"] = (latest_price / ma60 - 1.0) * 100.0

    return context


def _get_first(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    normalized = {str(key).strip().lower(): value for key, value in row.items()}
    for key in aliases:
        value = normalized.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _infer_market(code: str, market_type: str | None) -> str:
    market = str(market_type or "").strip().lower()
    if market in {"cn", "us", "hk"}:
        return market

    code_text = str(code or "").strip().upper()
    if code_text.endswith(".HK") or (code_text.isdigit() and len(code_text) == 5 and code_text.startswith("0")):
        return "hk"
    if "." in code_text and code_text.split(".")[-1].isalpha():
        return "us"
    if code_text.isdigit() and len(code_text) == 6:
        return "cn"
    return ""


def _storage_symbol(code: str, market: str, query: str) -> str:
    code_text = str(code or query or "").strip().upper()
    if market == "us":
        return code_text.split(".")[-1].replace(".US", "")
    if market == "hk":
        base = code_text.replace(".HK", "")
        if base.isdigit():
            return f"{base[-4:].zfill(4)}.HK"
        return code_text if code_text.endswith(".HK") else f"{code_text}.HK"
    if market == "cn":
        return code_text.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    return code_text


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("%", "")
        if cleaned in {"-", "--", "N/A", "nan"}:
            return None
        multiplier = 1.0
        if cleaned.endswith("亿"):
            multiplier = 100_000_000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("万"):
            multiplier = 10_000.0
            cleaned = cleaned[:-1]
        try:
            return float(cleaned) * multiplier
        except ValueError:
            return None
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _fmt_number(value: Any, digits: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.{digits}f}"


def _fmt_signed_number(value: Any, digits: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.{digits}f}"


def _fmt_percent(value: Any, digits: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.{digits}f}%"


def _fmt_signed_percent(value: Any, digits: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.{digits}f}%"


def _fmt_large(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    abs_value = abs(numeric)
    if abs_value >= 100_000_000:
        return f"{numeric / 100_000_000:.2f}亿"
    if abs_value >= 10_000:
        return f"{numeric / 10_000:.2f}万"
    return f"{numeric:.0f}"


def _fmt_money(value: Any) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return "N/A"
    abs_value = abs(numeric)
    if abs_value >= 100_000_000:
        return f"{numeric / 100_000_000:.2f}亿元"
    if abs_value >= 10_000:
        return f"{numeric / 10_000:.2f}万元"
    return f"{numeric:.2f}"
