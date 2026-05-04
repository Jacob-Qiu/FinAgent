"""Extension-layer data pipeline modules for FinAgent."""

from .market_data import HistoricalMarketDataPipeline
from .settings import ExtensionSettings, KnowledgeBaseSettings, load_extension_settings
from .universe import UniverseEntry, load_universe, select_entries

__all__ = [
    "ExtensionSettings",
    "HistoricalMarketDataPipeline",
    "KnowledgeBaseSettings",
    "UniverseEntry",
    "load_extension_settings",
    "load_universe",
    "select_entries",
]


def __getattr__(name: str):
    if name == "KnowledgeBasePipeline":
        from .knowledge_base import KnowledgeBasePipeline

        return KnowledgeBasePipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
