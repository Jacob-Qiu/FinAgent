"""Local historical market-data snapshot and semantic interpreter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import pandas as pd

from data_pipeline.settings import load_extension_settings
from data_pipeline.storage import read_parquet
from data_pipeline.universe import load_universe, select_entries


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value).strip()).casefold()


def _normalize_symbol_for_path(symbol: str) -> str:
    return str(symbol).strip().replace("/", "_").upper()


def _canonicalize_market_symbol(market: str, symbol: str) -> str:
    market_lower = str(market).strip().lower()
    raw = str(symbol).strip().upper()

    if market_lower == "cn":
        for suffix in (".SH", ".SZ", ".BJ"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
        return raw

    if market_lower == "hk":
        if raw.endswith(".HK"):
            raw = raw[:-3]
        if raw.isdigit():
            raw = raw.zfill(4)
        return f"{raw}.HK"

    if market_lower == "us":
        if raw.endswith(".US"):
            raw = raw[:-3]
        return raw

    return raw


@dataclass(frozen=True)
class ResolvedMarketTarget:
    market: str
    symbol: str
    name: str
    theme: str


def _entry_aliases(entry) -> set[str]:
    aliases = {
        _normalize_text(entry.symbol),
        _normalize_text(entry.name),
    }

    market_lower = entry.market.lower()
    canonical_symbol = _canonicalize_market_symbol(entry.market, entry.symbol)
    aliases.add(_normalize_text(canonical_symbol))

    if market_lower == "hk":
        base = canonical_symbol.replace(".HK", "")
        aliases.add(_normalize_text(base))
        aliases.add(_normalize_text(base.lstrip("0") or base))
    elif market_lower == "cn":
        aliases.add(_normalize_text(entry.symbol.zfill(6)))

    return aliases


def _resolve_target(query: str, market_type: str | None = None) -> ResolvedMarketTarget | None:
    entries = load_universe()
    if market_type:
        entries = select_entries(entries, market=market_type)

    query_norm = _normalize_text(query)
    exact_matches = []
    fuzzy_matches = []

    for entry in entries:
        aliases = _entry_aliases(entry)
        if query_norm in aliases:
            exact_matches.append(entry)
            continue

        name_norm = _normalize_text(entry.name)
        symbol_norm = _normalize_text(entry.symbol)
        if query_norm and (
            query_norm in name_norm
            or name_norm in query_norm
            or query_norm in symbol_norm
            or symbol_norm in query_norm
        ):
            fuzzy_matches.append(entry)

    chosen = exact_matches or fuzzy_matches
    if not chosen:
        # Last-resort heuristic: direct market/code style input.
        if market_type:
            inferred_symbol = _canonicalize_market_symbol(market_type, query)
            for entry in entries:
                if _normalize_text(entry.symbol) == _normalize_text(inferred_symbol):
                    return ResolvedMarketTarget(
                        market=entry.market.lower(),
                        symbol=entry.symbol,
                        name=entry.name,
                        theme=entry.theme,
                    )
        return None

    # Prefer the most precise hit; if there are multiple, keep the first exact hit.
    entry = chosen[0]
    return ResolvedMarketTarget(
        market=entry.market.lower(),
        symbol=entry.symbol,
        name=entry.name,
        theme=entry.theme,
    )


def _resolve_parquet_path(settings, target: ResolvedMarketTarget, interval: str) -> Path:
    market = target.market.lower()
    interval_lower = str(interval).strip().lower()
    file_name = f"{_normalize_symbol_for_path(target.symbol)}.parquet"
    return settings.storage.market_data_dir / market / interval_lower / file_name


def _safe_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _safe_dt(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value)
    except Exception:
        return None


def _fmt_number(value: Any, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.{digits}f}"


def _fmt_percent(value: Any, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    return f"{numeric:.{digits}f}%"


def _fmt_signed_percent(value: Any, digits: int = 2) -> str:
    numeric = _safe_float(value)
    if numeric is None:
        return "N/A"
    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.{digits}f}%"


class FinancialDataInterpreter:
    """Turn technical indicators into a compact, model-friendly evidence block."""

    def __init__(self, code: str, market: str, interval: str, source_path: Path):
        self.code = str(code)
        self.market = str(market).lower()
        self.interval = str(interval).lower()
        self.source_path = source_path

    def interpret(
        self,
        frame: pd.DataFrame,
        lookback_rows: int = 120,
        include_raw_tail: bool = False,
        tail_rows: int = 5,
    ) -> str:
        if frame.empty:
            return self._no_data_message("数据表为空。")

        working = frame.copy()
        if "date" not in working.columns:
            return self._no_data_message("缺少 date 字段，无法生成历史行情摘要。")

        working["date"] = pd.to_datetime(working["date"], errors="coerce")
        working = working.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
        if working.empty:
            return self._no_data_message("所有日期字段都无法解析。")

        if lookback_rows and lookback_rows > 0:
            working = working.tail(int(lookback_rows)).reset_index(drop=True)

        latest = working.iloc[-1]
        prev = working.iloc[-2] if len(working) > 1 else None

        sections = [
            self._build_header(working, latest),
            self._build_price_block(working, latest, prev),
            self._build_trend_block(latest, prev),
            self._build_rsi_block(latest),
            self._build_macd_block(latest, prev),
            self._build_boll_block(latest),
            self._build_volume_block(working, latest),
            self._build_summary_block(working, latest, prev),
            self._build_prompt_hint(),
        ]

        if include_raw_tail:
            sections.append(self._build_raw_tail_block(working, tail_rows=max(int(tail_rows), 1)))

        return "\n\n".join(section for section in sections if section)

    def _no_data_message(self, reason: str) -> str:
        return "\n".join(
            [
                f"### 【{self.code}】历史行情技术面快照",
                f"- 市场: {self.market}",
                f"- 周期: {self.interval}",
                f"- 数据文件: {self.source_path}",
                f"- 结果: {reason}",
                "",
                "【给下游模型的提示】",
                "这是一个未能成功解析的行情证据块。请先确认本地 Parquet 是否已生成，再重新请求历史行情快照。",
            ]
        )

    def _build_header(self, frame: pd.DataFrame, latest: pd.Series) -> str:
        latest_date = _safe_dt(latest.get("date"))
        start_date = _safe_dt(frame.iloc[0].get("date"))
        end_date = _safe_dt(frame.iloc[-1].get("date"))
        parts = [
            f"### 【{self.code}】历史行情技术面快照",
            f"- 市场: {self.market}",
            f"- 周期: {self.interval}",
            f"- 数据文件: {self.source_path}",
            f"- 样本行数: {len(frame)}",
            f"- 覆盖区间: {start_date.strftime('%Y-%m-%d') if start_date is not None else 'N/A'} ~ {end_date.strftime('%Y-%m-%d') if end_date is not None else 'N/A'}",
            f"- 截至日期: {latest_date.strftime('%Y-%m-%d') if latest_date is not None else 'N/A'}",
        ]
        return "\n".join(parts)

    def _build_price_block(
        self,
        frame: pd.DataFrame,
        latest: pd.Series,
        prev: pd.Series | None,
    ) -> str:
        close = _safe_float(latest.get("close"))
        prev_close = _safe_float(prev.get("close")) if prev is not None else None
        change_pct = None
        if close is not None and prev_close not in (None, 0):
            change_pct = ((close - prev_close) / prev_close) * 100

        ma20 = _safe_float(latest.get("ma_20"))
        ma20_bias = None
        if close is not None and ma20 not in (None, 0):
            ma20_bias = ((close - ma20) / ma20) * 100

        lines = [
            "#### 1. 价格概览",
            f"- 最新收盘价: {_fmt_number(close)}",
            f"- 相对前收涨跌: {_fmt_signed_percent(change_pct)}",
            f"- 20日均线乖离: {_fmt_signed_percent(ma20_bias)}",
        ]
        return "\n".join(lines)

    def _build_trend_block(self, latest: pd.Series, prev: pd.Series | None) -> str:
        ma5 = _safe_float(latest.get("ma_5"))
        ma10 = _safe_float(latest.get("ma_10"))
        ma20 = _safe_float(latest.get("ma_20"))
        ma60 = _safe_float(latest.get("ma_60"))
        close = _safe_float(latest.get("close"))

        if None in (ma5, ma10, ma20, ma60):
            return "\n".join(
                [
                    "#### 2. 趋势与均线",
                    "- 均线数据不足，当前样本可能还没有覆盖完整的 60 日窗口。",
                ]
            )

        if ma5 > ma10 > ma20 > ma60:
            trend = "多头排列，趋势偏强。"
            trend_score = 2
        elif ma5 < ma10 < ma20 < ma60:
            trend = "空头排列，趋势偏弱。"
            trend_score = -2
        else:
            trend = "均线缠绕，处于震荡或过渡阶段。"
            trend_score = 0

        price_side = "位于20日线之上" if close is not None and close > ma20 else "接近或低于20日线"
        ma20_slope = None
        if prev is not None:
            prev_ma20 = _safe_float(prev.get("ma_20"))
            if ma20 is not None and prev_ma20 not in (None, 0):
                ma20_slope = ((ma20 - prev_ma20) / prev_ma20) * 100

        slope_text = "N/A"
        if ma20_slope is not None:
            slope_text = "抬升" if ma20_slope > 0 else "下行" if ma20_slope < 0 else "走平"

        return "\n".join(
            [
                "#### 2. 趋势与均线",
                f"- 结构判断: {trend}",
                f"- 当前价格{price_side}，20日线斜率: {slope_text}",
                f"- 均线状态评分: {trend_score:+d}",
            ]
        )

    def _build_rsi_block(self, latest: pd.Series) -> str:
        rsi = _safe_float(latest.get("rsi_14"))
        if rsi is None:
            return "\n".join(
                [
                    "#### 3. 强弱指标 (RSI)",
                    "- RSI 数据不足，无法判断超买/超卖状态。",
                ]
            )

        if rsi >= 80:
            status = "极度超买，短线回撤风险较高。"
            score = -1
        elif rsi >= 70:
            status = "超买区，需警惕短线波动。"
            score = -1
        elif rsi > 55:
            status = "偏强区，买盘力量相对占优。"
            score = 1
        elif rsi >= 45:
            status = "中性区间，多空力量相对平衡。"
            score = 0
        elif rsi >= 30:
            status = "偏弱区，空方仍占优但未到极端。"
            score = -1
        else:
            status = "超卖区，存在技术性反弹预期，但趋势可能仍弱。"
            score = 1

        return "\n".join(
            [
                "#### 3. 强弱指标 (RSI)",
                f"- RSI(14): {_fmt_number(rsi)}，{status}",
                f"- RSI 评分: {score:+d}",
            ]
        )

    def _build_macd_block(self, latest: pd.Series, prev: pd.Series | None) -> str:
        diff = _safe_float(latest.get("macd_line"))
        dea = _safe_float(latest.get("macd_signal"))
        hist = _safe_float(latest.get("macd_hist"))

        if None in (diff, dea, hist):
            return "\n".join(
                [
                    "#### 4. 动能指标 (MACD)",
                    "- MACD 数据不足，无法形成可靠动能判断。",
                ]
            )

        if diff > dea:
            cross_state = "金叉维持或已形成，偏多。"
            score = 2
        elif diff < dea:
            cross_state = "死叉维持或已形成，偏空。"
            score = -2
        else:
            cross_state = "MACD 与信号线接近，方向尚未明确。"
            score = 0

        momentum_state = "动能增强" if hist > 0 else "动能减弱"
        if prev is not None:
            prev_hist = _safe_float(prev.get("macd_hist"))
            if prev_hist is not None and hist > prev_hist:
                momentum_state = "柱体扩张，动能增强"
            elif prev_hist is not None and hist < prev_hist:
                momentum_state = "柱体收缩，动能走弱"

        return "\n".join(
            [
                "#### 4. 动能指标 (MACD)",
                f"- DIF/DEA: {_fmt_number(diff, 4)} / {_fmt_number(dea, 4)}，{cross_state}",
                f"- MACD 柱状线: {_fmt_number(hist, 4)}，{momentum_state}",
                f"- MACD 评分: {score:+d}",
            ]
        )

    def _build_boll_block(self, latest: pd.Series) -> str:
        upper = _safe_float(latest.get("boll_upper"))
        mid = _safe_float(latest.get("boll_mid"))
        lower = _safe_float(latest.get("boll_lower"))
        close = _safe_float(latest.get("close"))

        if None in (upper, mid, lower, close):
            return "\n".join(
                [
                    "#### 5. 波动率 (Bollinger)",
                    "- 布林带数据不足，无法判断波动区间。",
                ]
            )

        if close >= upper:
            position = "触及上轨，偏强但超买风险上升。"
            score = 1
        elif close <= lower:
            position = "触及下轨，偏弱但可能接近支撑区。"
            score = -1
        elif close > mid:
            position = "位于中轨上方，价格偏强。"
            score = 1
        else:
            position = "位于中轨下方，价格偏弱。"
            score = -1

        bandwidth = None
        if mid not in (None, 0):
            bandwidth = (upper - lower) / mid

        if bandwidth is None:
            band_text = "N/A"
        elif bandwidth >= 0.20:
            band_text = "通道较宽，波动明显放大。"
        elif bandwidth <= 0.08:
            band_text = "通道收敛，后续可能面临方向选择。"
        else:
            band_text = "通道宽度适中，波动处于常态。"

        return "\n".join(
            [
                "#### 5. 波动率 (Bollinger)",
                f"- 价格位置: {position}",
                f"- 布林带带宽: {_fmt_percent(bandwidth * 100 if bandwidth is not None else None)}，{band_text}",
                f"- Bollinger 评分: {score:+d}",
            ]
        )

    def _build_volume_block(self, frame: pd.DataFrame, latest: pd.Series) -> str:
        if "volume" not in frame.columns:
            return ""

        volume = _safe_float(latest.get("volume"))
        if volume is None:
            return "\n".join(
                [
                    "#### 6. 量能",
                    "- 最新成交量缺失，暂无法判断放量/缩量状态。",
                ]
            )

        volume_avg_20 = None
        if len(frame) >= 2:
            volume_avg_20 = pd.to_numeric(frame["volume"], errors="coerce").tail(20).mean()

        if volume_avg_20 not in (None, 0) and not pd.isna(volume_avg_20):
            ratio = volume / float(volume_avg_20)
            if ratio >= 1.8:
                desc = "明显放量，趋势有效性更强。"
                score = 1
            elif ratio <= 0.7:
                desc = "缩量，市场参与度偏弱。"
                score = -1
            else:
                desc = "量能正常，未出现极端放大或萎缩。"
                score = 0
            ratio_text = f"{ratio:.2f}x"
        else:
            desc = "缺少足够的历史成交量窗口，无法计算20日均量比。"
            score = 0
            ratio_text = "N/A"

        return "\n".join(
            [
                "#### 6. 量能",
                f"- 最新成交量: {_fmt_number(volume, 0)}",
                f"- 20日量比: {ratio_text}",
                f"- 量能判断: {desc}",
                f"- 量能评分: {score:+d}",
            ]
        )

    def _build_summary_block(self, frame: pd.DataFrame, latest: pd.Series, prev: pd.Series | None) -> str:
        score = 0
        reasons: list[str] = []

        # Trend
        ma5 = _safe_float(latest.get("ma_5"))
        ma10 = _safe_float(latest.get("ma_10"))
        ma20 = _safe_float(latest.get("ma_20"))
        ma60 = _safe_float(latest.get("ma_60"))
        close = _safe_float(latest.get("close"))

        if None not in (ma5, ma10, ma20, ma60):
            if ma5 > ma10 > ma20 > ma60:
                score += 2
                reasons.append("均线多头排列")
            elif ma5 < ma10 < ma20 < ma60:
                score -= 2
                reasons.append("均线空头排列")

        if close is not None and ma20 not in (None, 0):
            if close > ma20:
                score += 1
                reasons.append("价格位于20日线之上")
            else:
                score -= 1
                reasons.append("价格位于20日线之下")

        rsi = _safe_float(latest.get("rsi_14"))
        if rsi is not None:
            if 45 <= rsi <= 65:
                score += 1
                reasons.append("RSI处于健康偏强区")
            elif rsi >= 75:
                score -= 1
                reasons.append("RSI过热")
            elif rsi <= 25:
                score += 1
                reasons.append("RSI过度超卖")

        diff = _safe_float(latest.get("macd_line"))
        dea = _safe_float(latest.get("macd_signal"))
        hist = _safe_float(latest.get("macd_hist"))
        if None not in (diff, dea, hist):
            if diff > dea and hist > 0:
                score += 2
                reasons.append("MACD偏多且柱体为正")
            elif diff < dea and hist < 0:
                score -= 2
                reasons.append("MACD偏空且柱体为负")

        upper = _safe_float(latest.get("boll_upper"))
        mid = _safe_float(latest.get("boll_mid"))
        lower = _safe_float(latest.get("boll_lower"))
        if None not in (upper, mid, lower, close):
            if close > mid:
                score += 1
                reasons.append("价格位于布林中轨上方")
            else:
                score -= 1
                reasons.append("价格位于布林中轨下方")

            if close >= upper:
                score -= 1
                reasons.append("触及布林上轨，短线需防回撤")
            elif close <= lower:
                score += 1
                reasons.append("触及布林下轨，存在支撑/反弹预期")

        if "volume" in frame.columns:
            volume = _safe_float(latest.get("volume"))
            if volume is not None and len(frame) >= 2:
                volume_avg_20 = pd.to_numeric(frame["volume"], errors="coerce").tail(20).mean()
                if volume_avg_20 not in (None, 0) and not pd.isna(volume_avg_20):
                    ratio = volume / float(volume_avg_20)
                    if ratio >= 1.8:
                        score += 1
                        reasons.append("放量确认")
                    elif ratio <= 0.7:
                        score -= 1
                        reasons.append("缩量观望")

        if score >= 5:
            advice = "强势看多，适合继续跟踪趋势延续。"
            label = "强势偏多"
        elif score >= 2:
            advice = "偏多，但仍需要结合新闻/研报确认。"
            label = "偏多跟踪"
        elif score >= -1:
            advice = "中性观望，等待更明确的方向确认。"
            label = "中性整理"
        elif score >= -4:
            advice = "偏空谨慎，回撤风险较高。"
            label = "偏空谨慎"
        else:
            advice = "风险偏高，暂不建议追随单边方向。"
            label = "高风险偏空"

        completeness = []
        for key in ("ma_5", "ma_10", "ma_20", "ma_60", "rsi_14", "macd_line", "macd_signal", "macd_hist", "boll_upper", "boll_mid", "boll_lower"):
            if key in latest.index and pd.notna(latest.get(key)):
                completeness.append(key)

        confidence = "高" if len(completeness) >= 8 else "中" if len(completeness) >= 5 else "低"

        return "\n".join(
            [
                "#### 7. 综合判断",
                f"- 技术面综合评分: {score:+d}",
                f"- 综合偏向: {label}",
                f"- 信号置信度: {confidence}",
                f"- 结论建议: {advice}",
                f"- 核心依据: {'；'.join(reasons) if reasons else '可用指标较少，综合判断偏保守'}",
            ]
        )

    def _build_prompt_hint(self) -> str:
        return "\n".join(
            [
                "### 给下游模型的提示",
                "- 这是经过语义映射后的历史行情证据块，不是原始指标表。",
                "- 优先结合趋势、动能、波动和量能四个维度判断，不要只看单一指标。",
                "- 如果指标之间存在明显分歧，请输出“分歧/等待确认”，不要强行给单边结论。",
                "- 这类历史技术面应与新闻、研报和基本面一起使用。",
            ]
        )

    def _build_raw_tail_block(self, frame: pd.DataFrame, tail_rows: int = 5) -> str:
        tail = frame.tail(tail_rows).copy()
        columns = [column for column in ["date", "close", "ma_20", "rsi_14", "macd_hist", "boll_mid", "boll_upper", "boll_lower", "volume"] if column in tail.columns]
        if not columns:
            return ""

        tail = tail[columns]
        for column in tail.columns:
            if column == "date":
                tail[column] = pd.to_datetime(tail[column], errors="coerce").dt.strftime("%Y-%m-%d")
            else:
                tail[column] = pd.to_numeric(tail[column], errors="coerce")

        def _cell(value: Any) -> str:
            numeric = _safe_float(value)
            if numeric is not None:
                return f"{numeric:.4f}" if abs(numeric) < 100 else f"{numeric:.2f}"
            if pd.isna(value):
                return "N/A"
            return str(value)

        header = "| " + " | ".join(columns) + " |"
        separator = "| " + " | ".join(["---"] * len(columns)) + " |"
        rows = [
            "| " + " | ".join(_cell(row[column]) for column in columns) + " |"
            for _, row in tail.iterrows()
        ]

        return "\n".join(
            [
                "#### 附录: 最近样本行",
                header,
                separator,
                *rows,
            ]
        )


def market_data_snapshot(
    query: str,
    market_type: str | None = None,
    interval: str = "daily",
    as_of_date: str | None = None,
    lookback_rows: int = 120,
    include_raw_tail: bool = False,
    tail_rows: int = 5,
) -> str:
    """Read a local Parquet file and turn it into an LLM-friendly evidence block."""

    settings = load_extension_settings()
    target = _resolve_target(query, market_type=market_type)
    if target is None:
        available_markets = ", ".join(sorted({entry.market for entry in load_universe()}))
        return "\n".join(
            [
                "### 历史行情技术面快照",
                f"- 查询词: {query}",
                f"- 市场类型: {market_type or '未指定'}",
                "- 结果: 无法在本地股票池中定位该标的。",
                f"- 可用市场: {available_markets}",
                "- 建议: 请提供更精确的公司名称、ticker 或明确市场类型；如果本地还没建仓数据，请先运行 build-history。",
            ]
        )

    path = _resolve_parquet_path(settings, target, interval)
    if not path.exists():
        return "\n".join(
            [
                f"### 【{target.symbol}】历史行情技术面快照",
                f"- 市场: {target.market}",
                f"- 周期: {interval}",
                f"- 数据文件: {path}",
                "- 结果: 本地 Parquet 文件不存在。",
                "- 建议: 请先运行历史行情构建任务，例如 build-history，生成对应 market/interval 的 Parquet。",
            ]
        )

    try:
        frame = read_parquet(path)
    except Exception as exc:
        return "\n".join(
            [
                f"### 【{target.symbol}】历史行情技术面快照",
                f"- 市场: {target.market}",
                f"- 周期: {interval}",
                f"- 数据文件: {path}",
                f"- 结果: 读取 Parquet 失败，原因: {exc}",
            ]
        )

    if "date" in frame.columns and as_of_date:
        cutoff = pd.to_datetime(as_of_date, errors="coerce")
        if pd.notna(cutoff):
            frame = frame[pd.to_datetime(frame["date"], errors="coerce") <= cutoff]

    interpreter = FinancialDataInterpreter(
        code=target.symbol,
        market=target.market,
        interval=interval,
        source_path=path,
    )
    return interpreter.interpret(
        frame=frame,
        lookback_rows=lookback_rows,
        include_raw_tail=include_raw_tail,
        tail_rows=tail_rows,
    )
