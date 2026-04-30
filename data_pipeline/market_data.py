"""Historical market data pipeline for extension-layer assets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .settings import ExtensionSettings, load_extension_settings
from .storage import ensure_directory, read_parquet, write_parquet


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _format_date(value: date | None) -> str | None:
    return value.strftime("%Y-%m-%d") if value else None


def _format_cn_date(value: date | None) -> str | None:
    return value.strftime("%Y%m%d") if value else None


def _normalize_symbol_for_path(symbol: str) -> str:
    return symbol.replace("/", "_")


DAILY_INCREMENTAL_BACKFILL_DAYS = 120
WEEKLY_INCREMENTAL_BACKFILL_DAYS = 540


def _hk_symbol_for_akshare(symbol: str) -> str:
    base_symbol = symbol.split(".")[0].strip()
    return base_symbol.zfill(5)


def _infer_cn_exchange(symbol: str) -> str:
    if symbol.startswith(("600", "601", "603", "605", "688", "689", "900")):
        return "SH"
    if symbol.startswith(("000", "001", "002", "003", "200", "300", "301")):
        return "SZ"
    if symbol.startswith(("430", "440", "830", "831", "832", "833", "835", "836", "837", "838", "839", "870", "871", "872", "873", "874", "875", "876", "877", "878", "879")):
        return "BJ"
    raise ValueError(f"Unable to infer A-share exchange for symbol: {symbol}")


@dataclass(frozen=True)
class FetchResult:
    market: str
    symbol: str
    interval: str
    rows: int
    path: Path
    provider: str


class HistoricalMarketDataPipeline:
    """Download, enrich, and store daily/weekly market data as Parquet."""

    def __init__(self, settings: ExtensionSettings | None = None):
        self.settings = settings or load_extension_settings()
        ensure_directory(self.settings.storage.market_data_dir)

    def build_universe(
        self,
        entries,
        intervals: list[str],
        start_date: str = "2018-01-01",
        end_date: str | None = None,
        refresh_mode: str = "incremental",
    ) -> list[FetchResult]:
        results: list[FetchResult] = []
        failures: list[str] = []
        for entry in entries:
            for interval in intervals:
                try:
                    results.append(
                        self.build_one(
                            symbol=entry.symbol,
                            market=entry.market,
                            interval=interval,
                            start_date=start_date,
                            end_date=end_date,
                            refresh_mode=refresh_mode,
                        )
                    )
                except Exception as exc:
                    failures.append(f"{entry.market}:{entry.symbol} {interval} -> {exc}")
        if failures:
            print("Some market-data assets failed and were skipped:")
            for failure in failures:
                print(f"  - {failure}")
        return results

    def build_one(
        self,
        symbol: str,
        market: str,
        interval: str,
        start_date: str = "2018-01-01",
        end_date: str | None = None,
        refresh_mode: str = "incremental",
    ) -> FetchResult:
        storage_path = self._storage_path(market, interval, symbol)
        effective_start = _parse_date(start_date)
        effective_end = _parse_date(end_date) or date.today()

        existing = None
        if storage_path.exists() and refresh_mode != "full":
            existing = read_parquet(storage_path)
            if not existing.empty and "date" in existing.columns:
                last_date = existing["date"].max()
                if hasattr(last_date, "date"):
                    last_date = last_date.date()
                buffer_days = self._incremental_backfill_days(interval)
                effective_start = max(effective_start, last_date - timedelta(days=buffer_days))

        frame, provider = self._fetch_market_data(
            symbol=symbol,
            market=market,
            interval=interval,
            start_date=effective_start,
            end_date=effective_end,
        )

        if frame.empty:
            raise RuntimeError(f"No market data returned for {market}:{symbol} ({interval})")

        enriched = self._enrich_frame(frame, market=market, symbol=symbol, interval=interval)
        merged = self._merge_existing(existing, enriched)
        write_parquet(merged, storage_path)

        return FetchResult(
            market=market,
            symbol=symbol,
            interval=interval,
            rows=len(merged),
            path=storage_path,
            provider=provider,
        )

    def _storage_path(self, market: str, interval: str, symbol: str) -> Path:
        normalized_symbol = _normalize_symbol_for_path(symbol)
        return self.settings.storage.market_data_dir / market / interval / f"{normalized_symbol}.parquet"

    @staticmethod
    def _incremental_backfill_days(interval: str) -> int:
        if interval == "weekly":
            return WEEKLY_INCREMENTAL_BACKFILL_DAYS
        return DAILY_INCREMENTAL_BACKFILL_DAYS

    def _fetch_market_data(
        self,
        symbol: str,
        market: str,
        interval: str,
        start_date: date,
        end_date: date,
    ):
        market_lower = market.lower()
        if market_lower == "cn":
            frame = self._fetch_cn_with_akshare(symbol, interval, start_date, end_date)
            if frame.empty:
                raise RuntimeError(f"Unable to fetch CN market data for {symbol} ({interval}). AkShare returned no rows.")
            return frame, "akshare"

        if market_lower == "us":
            frame = self._fetch_us_with_akshare(symbol, interval, start_date, end_date)
            if frame.empty:
                raise RuntimeError(f"Unable to fetch US market data for {symbol} ({interval}). AkShare returned no rows.")
            return frame, "akshare"

        if market_lower == "hk":
            frame = self._fetch_hk_with_akshare(symbol, interval, start_date, end_date)
            if frame.empty:
                raise RuntimeError(f"Unable to fetch HK market data for {symbol} ({interval}). AkShare returned no rows.")
            return frame, "akshare"

        raise ValueError(f"Unsupported market: {market}")

    def _fetch_us_with_akshare(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
    ):
        import akshare as ak

        frame = ak.stock_us_daily(symbol=symbol, adjust="")
        normalized = self._normalize_akshare_equity_frame(
            frame=frame,
            symbol=symbol,
            market="us",
            start_date=start_date,
            end_date=end_date,
        )
        if interval == "weekly":
            normalized = self._resample_weekly_frame(normalized)
        return normalized

    def _fetch_hk_with_akshare(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
    ):
        import akshare as ak

        frame = ak.stock_hk_daily(symbol=_hk_symbol_for_akshare(symbol), adjust="")
        normalized = self._normalize_akshare_equity_frame(
            frame=frame,
            symbol=symbol,
            market="hk",
            start_date=start_date,
            end_date=end_date,
        )
        if interval == "weekly":
            normalized = self._resample_weekly_frame(normalized)
        return normalized

    def _normalize_akshare_equity_frame(
        self,
        frame,
        symbol: str,
        market: str,
        start_date: date,
        end_date: date,
    ):
        import pandas as pd

        if frame is None or frame.empty:
            return pd.DataFrame()

        rename_map = {
            "date": "date",
            "Date": "date",
            "Datetime": "date",
            "日期": "date",
            "open": "open",
            "Open": "open",
            "开盘": "open",
            "high": "high",
            "High": "high",
            "最高": "high",
            "low": "low",
            "Low": "low",
            "最低": "low",
            "close": "close",
            "Close": "close",
            "收盘": "close",
            "adj_close": "adj_close",
            "Adj Close": "adj_close",
            "volume": "volume",
            "Volume": "volume",
            "成交量": "volume",
            "amount": "amount",
            "成交额": "amount",
            "change": "change",
            "涨跌额": "change",
            "pct_change": "pct_change",
            "涨跌幅": "pct_change",
            "turnover_rate": "turnover_rate",
            "换手率": "turnover_rate",
        }

        normalized = frame.rename(columns=rename_map).copy()
        if "date" not in normalized.columns:
            raise RuntimeError(f"Unexpected AkShare columns for {market}:{symbol}: {list(frame.columns)}")

        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        normalized = normalized.dropna(subset=["date"])
        normalized = self._filter_by_date(normalized, start_date, end_date)
        normalized["symbol"] = symbol
        normalized["market"] = market
        return normalized

    @staticmethod
    def _filter_by_date(frame, start_date: date, end_date: date):
        import pandas as pd

        filtered = frame.copy()
        filtered["date"] = pd.to_datetime(filtered["date"], errors="coerce")
        filtered = filtered.dropna(subset=["date"])
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        mask = (filtered["date"] >= start_ts) & (filtered["date"] <= end_ts)
        return filtered.loc[mask].reset_index(drop=True)

    @staticmethod
    def _resample_weekly_frame(frame):
        import pandas as pd

        if frame is None or frame.empty:
            return pd.DataFrame()

        working = frame.copy()
        working["date"] = pd.to_datetime(working["date"], errors="coerce")
        working = working.dropna(subset=["date"]).sort_values("date")

        aggregations = {}
        if "open" in working.columns:
            aggregations["open"] = "first"
        if "high" in working.columns:
            aggregations["high"] = "max"
        if "low" in working.columns:
            aggregations["low"] = "min"
        if "close" in working.columns:
            aggregations["close"] = "last"
        if "adj_close" in working.columns:
            aggregations["adj_close"] = "last"
        if "volume" in working.columns:
            aggregations["volume"] = "sum"
        if "amount" in working.columns:
            aggregations["amount"] = "sum"
        if "change" in working.columns:
            aggregations["change"] = "last"
        if "pct_change" in working.columns:
            aggregations["pct_change"] = "last"
        if "turnover_rate" in working.columns:
            aggregations["turnover_rate"] = "last"

        if not aggregations:
            return pd.DataFrame()

        weekly = (
            working.resample("W-FRI", on="date")
            .agg(aggregations)
            .dropna(how="all")
            .reset_index()
        )
        weekly["symbol"] = frame["symbol"].iloc[0] if "symbol" in frame.columns and not frame.empty else ""
        weekly["market"] = frame["market"].iloc[0] if "market" in frame.columns and not frame.empty else ""
        return weekly

    def _fetch_cn_with_akshare(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
    ):
        import akshare as ak
        import pandas as pd

        frame = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily" if interval == "daily" else "weekly",
            start_date=_format_cn_date(start_date),
            end_date=_format_cn_date(end_date),
            adjust="qfq",
        )
        if frame is None or frame.empty:
            return pd.DataFrame()

        rename_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "换手率": "turnover_rate",
        }
        normalized = frame.rename(columns=rename_map)
        if "date" not in normalized.columns:
            raise RuntimeError(f"Unexpected AkShare columns for {symbol}: {list(frame.columns)}")

        normalized["date"] = pd.to_datetime(normalized["date"])
        return normalized

    def _enrich_frame(self, frame, market: str, symbol: str, interval: str):
        import pandas as pd

        enriched = frame.copy()
        enriched = enriched.sort_values("date").reset_index(drop=True)
        enriched["market"] = market
        enriched["symbol"] = symbol
        enriched["interval"] = interval

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "change",
            "pct_change",
            "turnover_rate",
            "adj_close",
        ]
        for column in numeric_columns:
            if column in enriched.columns:
                enriched[column] = pd.to_numeric(enriched[column], errors="coerce")

        close_series = enriched["close"]
        enriched["ma_5"] = close_series.rolling(window=5).mean()
        enriched["ma_10"] = close_series.rolling(window=10).mean()
        enriched["ma_20"] = close_series.rolling(window=20).mean()
        enriched["ma_60"] = close_series.rolling(window=60).mean()
        enriched["rsi_14"] = self._rsi(close_series, period=14)

        macd_line, macd_signal, macd_hist = self._macd(close_series)
        enriched["macd_line"] = macd_line
        enriched["macd_signal"] = macd_signal
        enriched["macd_hist"] = macd_hist

        boll_mid, boll_upper, boll_lower = self._boll(close_series)
        enriched["boll_mid"] = boll_mid
        enriched["boll_upper"] = boll_upper
        enriched["boll_lower"] = boll_lower

        return enriched

    def _merge_existing(self, existing, fresh):
        import pandas as pd

        if existing is None or existing.empty:
            merged = fresh
        else:
            merged = pd.concat([existing, fresh], ignore_index=True)

        merged["date"] = pd.to_datetime(merged["date"])
        merged = merged.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        merged = merged.reset_index(drop=True)
        return merged

    @staticmethod
    def _rsi(close_series, period: int = 14):
        delta = close_series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, None)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _macd(close_series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = close_series.ewm(span=fast, adjust=False).mean()
        ema_slow = close_series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @staticmethod
    def _boll(close_series, window: int = 20, num_std: float = 2.0):
        mid = close_series.rolling(window=window).mean()
        std = close_series.rolling(window=window).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        return mid, upper, lower
