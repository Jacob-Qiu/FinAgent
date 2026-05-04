"""Stock universe loader for the extension layer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from .settings import load_extension_settings


@dataclass(frozen=True)
class UniverseEntry:
    market: str
    symbol: str
    name: str
    theme: str


def _default_universe_path() -> Path:
    settings = load_extension_settings()
    return settings.storage.kb_dir / "stock_universe.yaml"


def load_universe(path: str | Path | None = None) -> list[UniverseEntry]:
    universe_path = Path(path).expanduser() if path else _default_universe_path()
    with universe_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    entries: list[UniverseEntry] = []
    markets = raw.get("markets", {})
    for market, items in markets.items():
        for item in items or []:
            entries.append(
                UniverseEntry(
                    market=market,
                    symbol=str(item["symbol"]).strip(),
                    name=str(item["name"]).strip(),
                    theme=str(item["theme"]).strip(),
                )
            )
    return entries


def select_entries(
    entries: Iterable[UniverseEntry],
    market: str = "all",
    symbols: set[str] | None = None,
) -> list[UniverseEntry]:
    market_lower = market.lower()
    symbol_filter = {symbol.upper() for symbol in symbols or set()}
    selected: list[UniverseEntry] = []

    for entry in entries:
        if market_lower != "all" and entry.market.lower() != market_lower:
            continue
        if symbol_filter and entry.symbol.upper() not in symbol_filter:
            continue
        selected.append(entry)

    return selected
