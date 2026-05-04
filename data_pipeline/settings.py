"""Settings loader for the no-conflict extension layer."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config_ext.local.yml"
EXAMPLE_CONFIG_PATH = REPO_ROOT / "config_ext.example.yml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid configuration format in {path}")
    return data


def _deep_get(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


@dataclass(frozen=True)
class LLMProviderSettings:
    default_provider: str
    gemini_api_key: str
    gemini_model: str
    ollama_base_url: str
    ollama_model: str


@dataclass(frozen=True)
class DataSourceSettings:
    tushare_token: str
    finnhub_api_key: str
    qieman_url: str


@dataclass(frozen=True)
class StorageSettings:
    market_data_dir: Path
    kb_dir: Path


@dataclass(frozen=True)
class KnowledgeBaseSettings:
    raw_reports_dir: Path
    raw_filings_dir: Path
    raw_encyclopedia_dir: Path
    raw_glossary_dir: Path
    qdrant_path: Path
    qdrant_url: str
    qdrant_api_key: str
    collection_name: str
    embedding_model: str
    embedding_batch_size: int
    report_chunk_tokens: int
    report_chunk_overlap: int
    filing_chunk_tokens: int
    filing_chunk_overlap: int
    encyclopedia_chunk_tokens: int
    encyclopedia_chunk_overlap: int
    glossary_chunk_tokens: int
    glossary_chunk_overlap: int


@dataclass(frozen=True)
class ExtensionSettings:
    llm: LLMProviderSettings
    data_sources: DataSourceSettings
    storage: StorageSettings
    knowledge_base: KnowledgeBaseSettings


def load_extension_settings(config_path: str | Path | None = None) -> ExtensionSettings:
    """Load extension settings from local YAML with env overrides."""

    local_config_path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    example_config = _read_yaml(EXAMPLE_CONFIG_PATH)
    local_config = _read_yaml(local_config_path)

    def cfg(*keys: str, default: Any = None) -> Any:
        value = _deep_get(local_config, *keys, default=None)
        if value not in (None, ""):
            return value
        value = _deep_get(example_config, *keys, default=None)
        if value not in (None, ""):
            return value
        return default

    llm = LLMProviderSettings(
        default_provider=os.environ.get(
            "FINAGENT_EXT_DEFAULT_LLM",
            str(cfg("default_llm_provider", default="gemini")),
        ),
        gemini_api_key=os.environ.get(
            "GEMINI_API_KEY",
            str(cfg("gemini", "api_key", default="")),
        ),
        gemini_model=os.environ.get(
            "GEMINI_MODEL",
            str(cfg("gemini", "model", default="gemini-2.5-flash")),
        ),
        ollama_base_url=os.environ.get(
            "OLLAMA_BASE_URL",
            str(cfg("ollama", "base_url", default="http://localhost:11434/api/chat")),
        ),
        ollama_model=os.environ.get(
            "OLLAMA_MODEL",
            str(cfg("ollama", "model", default="qwen3")),
        ),
    )

    data_sources = DataSourceSettings(
        tushare_token=os.environ.get(
            "TUSHARE_TOKEN",
            str(cfg("data_sources", "tushare", "token", default="")),
        ),
        finnhub_api_key=os.environ.get(
            "FINNHUB_API_KEY",
            str(cfg("data_sources", "finnhub", "api_key", default="")),
        ),
        qieman_url=os.environ.get(
            "QIEMAN_URL",
            str(cfg("data_sources", "qieman", "url", default="")),
        ),
    )

    storage = StorageSettings(
        market_data_dir=REPO_ROOT
        / str(cfg("storage", "market_data_dir", default="data/market_data")),
        kb_dir=REPO_ROOT / str(cfg("storage", "kb_dir", default="kb")),
    )

    def resolve_path(value: Any, fallback: Path) -> Path:
        if value in (None, ""):
            return fallback
        path = Path(str(value)).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path

    knowledge_base = KnowledgeBaseSettings(
        raw_reports_dir=resolve_path(
            cfg("knowledge_base", "sources", "raw_reports_dir"),
            storage.kb_dir / "raw_reports",
        ),
        raw_filings_dir=resolve_path(
            cfg("knowledge_base", "sources", "raw_filings_dir"),
            storage.kb_dir / "raw_filings",
        ),
        raw_encyclopedia_dir=resolve_path(
            cfg("knowledge_base", "sources", "raw_encyclopedia_dir"),
            storage.kb_dir / "raw_encyclopedia",
        ),
        raw_glossary_dir=resolve_path(
            cfg("knowledge_base", "sources", "raw_glossary_dir"),
            storage.kb_dir / "raw_glossary",
        ),
        qdrant_path=resolve_path(
            cfg("knowledge_base", "qdrant", "path"),
            storage.kb_dir / "qdrant",
        ),
        qdrant_url=str(cfg("knowledge_base", "qdrant", "url", default="")),
        qdrant_api_key=str(cfg("knowledge_base", "qdrant", "api_key", default="")),
        collection_name=str(
            cfg("knowledge_base", "qdrant", "collection_name", default="finagent_kb")
        ),
        embedding_model=str(
            cfg("knowledge_base", "embedding", "model", default="BAAI/bge-m3")
        ),
        embedding_batch_size=int(
            cfg("knowledge_base", "embedding", "batch_size", default=32)
        ),
        report_chunk_tokens=int(
            cfg("knowledge_base", "chunking", "report_chunk_tokens", default=700)
        ),
        report_chunk_overlap=int(
            cfg("knowledge_base", "chunking", "report_chunk_overlap", default=120)
        ),
        filing_chunk_tokens=int(
            cfg("knowledge_base", "chunking", "filing_chunk_tokens", default=800)
        ),
        filing_chunk_overlap=int(
            cfg("knowledge_base", "chunking", "filing_chunk_overlap", default=120)
        ),
        encyclopedia_chunk_tokens=int(
            cfg("knowledge_base", "chunking", "encyclopedia_chunk_tokens", default=500)
        ),
        encyclopedia_chunk_overlap=int(
            cfg("knowledge_base", "chunking", "encyclopedia_chunk_overlap", default=80)
        ),
        glossary_chunk_tokens=int(
            cfg("knowledge_base", "chunking", "glossary_chunk_tokens", default=256)
        ),
        glossary_chunk_overlap=int(
            cfg("knowledge_base", "chunking", "glossary_chunk_overlap", default=32)
        ),
    )

    return ExtensionSettings(
        llm=llm,
        data_sources=data_sources,
        storage=storage,
        knowledge_base=knowledge_base,
    )
