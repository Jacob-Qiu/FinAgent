"""CLI to build historical market-data assets without touching legacy code."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_pipeline.market_data import HistoricalMarketDataPipeline
from data_pipeline.universe import load_universe, select_entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily/weekly market data as Parquet.")
    parser.add_argument(
        "--market",
        choices=["all", "us", "cn", "hk"],
        default="all",
        help="Restrict the run to one market.",
    )
    parser.add_argument(
        "--interval",
        choices=["daily", "weekly", "all"],
        default="all",
        help="Interval to build.",
    )
    parser.add_argument(
        "--symbols",
        default="",
        help="Comma-separated subset of symbols. Defaults to the whole configured universe.",
    )
    parser.add_argument(
        "--start-date",
        default="2018-01-01",
        help="Inclusive start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Inclusive end date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--refresh-mode",
        choices=["incremental", "full"],
        default="incremental",
        help="Incremental reuses existing Parquet files and only refreshes a recent buffer.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    intervals = ["daily", "weekly"] if args.interval == "all" else [args.interval]
    symbols = {item.strip().upper() for item in args.symbols.split(",") if item.strip()}

    entries = load_universe()
    selected = select_entries(entries, market=args.market, symbols=symbols or None)
    if not selected:
        print("No symbols selected. Check --market/--symbols against kb/stock_universe.yaml.")
        return 1

    pipeline = HistoricalMarketDataPipeline()
    results = pipeline.build_universe(
        entries=selected,
        intervals=intervals,
        start_date=args.start_date,
        end_date=args.end_date,
        refresh_mode=args.refresh_mode,
    )

    print(f"Built {len(results)} market-data assets.")
    for result in results:
        print(
            f"{result.market}:{result.symbol} {result.interval} "
            f"rows={result.rows} provider={result.provider} path={result.path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
