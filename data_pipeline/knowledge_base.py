"""Knowledge-base pipeline for reports, filings, encyclopedia entries, and glossary terms.

This module builds a source-aware RAG corpus:

- Financial reports: page / section aware chunking with token windows, plus a document summary chunk.
- Financial filings: page / section aware chunking with report-period and statement metadata.
- Financial encyclopedia: heading-aware chunking with token windows.
- Financial glossary: one-term-per-chunk normalization with token fallback.

Embeddings are produced with BGE-M3 and stored in Qdrant. A lightweight SQLite lexical index
tracks chunk-level term overlap so hybrid retrieval can combine semantic and keyword recall.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import csv
import html
import json
import os
import sqlite3
import re
import uuid
import warnings
from pathlib import Path
from typing import Any, Iterable, Sequence

warnings.filterwarnings("ignore", message="ARC4 has been moved")

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import tiktoken
import yaml

from .settings import ExtensionSettings, REPO_ROOT, load_extension_settings
from .storage import ensure_directory

try:
    from qdrant_client import QdrantClient
    from qdrant_client import models as qdrant_models
except ImportError as exc:  # pragma: no cover - handled at runtime
    QdrantClient = None  # type: ignore[assignment]
    qdrant_models = None  # type: ignore[assignment]
    QDRANT_IMPORT_ERROR = exc
else:  # pragma: no cover - import availability is environment-specific
    QDRANT_IMPORT_ERROR = None


SUPPORTED_REPORT_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
SUPPORTED_FILING_EXTENSIONS = {
    ".pdf",
    ".md",
    ".markdown",
    ".txt",
    ".html",
    ".htm",
    ".xhtml",
    ".xml",
    ".csv",
    ".json",
}
SUPPORTED_ENCYCLOPEDIA_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}
SUPPORTED_GLOSSARY_EXTENSIONS = {".csv", ".json", ".yaml", ".yml", ".md", ".markdown", ".txt"}

HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
CHINESE_CHAPTER_PATTERN = re.compile(r"^第([一二三四五六七八九十百千0-9]+)([章节篇部分])\s*(.*)$")
CHINESE_OUTLINE_PATTERN = re.compile(r"^([一二三四五六七八九十百千]+)[、.．]\s*(.+)$")
CHINESE_SUBOUTLINE_PATTERN = re.compile(r"^（([一二三四五六七八九十百千]+)）\s*(.+)$")
ARABIC_OUTLINE_PATTERN = re.compile(r"^(\d+(?:\.\d+)*)[、.．]\s*(.+)$")
GLOSSARY_TERM_PATTERN = re.compile(r"^\s*[-*+]\s*([^:：]{1,120})\s*[:：]\s*(.+?)\s*$")
REPORT_SUMMARY_PREVIEW_LIMIT = 8
REPORT_SUMMARY_MAX_CHARS = 1600
REPORT_SUMMARY_MODEL_INPUT_MAX_CHARS = 8000
REPORT_SUMMARY_MODEL_TIMEOUT_SECONDS = 600
CONTEXT_EXPANSION_TOKEN_LIMIT = 800
RERANK_DEDUP_SCORE_RATIO = 0.75
FILING_REPORT_TYPE_ALIASES = {
    "annual_report": {
        "annual",
        "annual_report",
        "yearly",
        "year_report",
        "10-k",
        "10k",
        "20-f",
        "20f",
        "年报",
        "年度报告",
        "全年",
    },
    "semiannual_report": {
        "semiannual",
        "semi_annual",
        "half_year",
        "half-year",
        "interim",
        "h1",
        "1h",
        "中报",
        "半年报",
        "半年度报告",
    },
    "quarterly_report": {
        "quarterly",
        "quarter",
        "q1",
        "q2",
        "q3",
        "q4",
        "10-q",
        "10q",
        "季报",
        "季度报告",
        "一季报",
        "三季报",
    },
    "earnings_flash": {
        "earnings_flash",
        "flash",
        "业绩快报",
        "快报",
    },
    "earnings_preannouncement": {
        "preannouncement",
        "pre_announcement",
        "forecast",
        "业绩预告",
        "预告",
    },
    "amendment": {
        "amendment",
        "amended",
        "correction",
        "更正",
        "修订",
    },
}
FILING_STATEMENT_KEYWORDS = {
    "balance_sheet": ("资产负债表", "财务状况表", "balance sheet", "statement of financial position"),
    "income_statement": ("利润表", "损益表", "综合收益表", "income statement", "profit and loss"),
    "cash_flow_statement": ("现金流量表", "cash flow"),
    "equity_statement": ("所有者权益", "股东权益", "权益变动", "changes in equity"),
    "notes": ("财务报表附注", "附注", "notes to"),
    "mdna": ("管理层讨论与分析", "经营情况讨论与分析", "management discussion", "md&a"),
    "risk_factors": ("风险因素", "主要风险", "risk factors"),
    "audit_report": ("审计报告", "auditor", "audit report"),
}


@dataclass(frozen=True)
class KnowledgeChunk:
    """A chunk ready for embedding and Qdrant storage."""

    id: str
    content: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class TextChunk:
    """Text chunk plus paragraph-local coordinates used for context expansion."""

    text: str
    token_count: int
    paragraph_index: int
    paragraph_chunk_index: int
    paragraph_chunk_total: int
    paragraph_token_count: int


@dataclass(frozen=True)
class KnowledgeBuildSummary:
    """Summary of a Qdrant build run."""

    collection_name: str
    total_chunks: int
    chunks_by_doc_type: dict[str, int]
    files_by_doc_type: dict[str, int]
    skipped_files: int


@dataclass(frozen=True)
class KnowledgeSearchHit:
    """A scored retrieval hit from the KB search pipeline."""

    id: str
    score: float
    content: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class KnowledgeQueryContext:
    """Normalized query state used by hybrid retrieval."""

    raw_query: str
    normalized_query: str
    search_terms: list[str]
    ticker: str | None
    publish_date: str | None
    period_end: str | None
    report_type: str | None
    statement_type: str | None


@dataclass(frozen=True)
class KnowledgeSearchCandidate:
    """A merged retrieval candidate before final expansion."""

    hit: KnowledgeSearchHit
    vector_score: float = 0.0
    lexical_score: float = 0.0
    fused_score: float = 0.0


class KnowledgeBasePipeline:
    """Build and query the finance knowledge base stored in Qdrant."""

    def __init__(self, settings: ExtensionSettings | None = None):
        self.settings = settings or load_extension_settings()
        self._embedding_model: SentenceTransformer | None = None
        self._qdrant_client: QdrantClient | None = None
        self._encoding = tiktoken.get_encoding("cl100k_base")

    @property
    def embedding_model(self) -> SentenceTransformer:
        if self._embedding_model is None:
            kb_embedding_online = os.environ.get("FINAGENT_KB_EMBEDDING_ONLINE") == "1"
            self._embedding_model = SentenceTransformer(
                self.settings.knowledge_base.embedding_model,
                local_files_only=not kb_embedding_online,
            )
        return self._embedding_model

    @property
    def qdrant_client(self) -> QdrantClient:
        if self._qdrant_client is None:
            self._qdrant_client = self._build_qdrant_client()
        return self._qdrant_client

    def build_collection(self, doc_types: Sequence[str] | None = None, rebuild: bool = False) -> KnowledgeBuildSummary:
        """Index the configured sources into Qdrant."""

        if not self._qdrant_available():
            raise RuntimeError(
                "qdrant-client is not installed. Install it before building the knowledge base."
            ) from QDRANT_IMPORT_ERROR

        normalized_doc_types = self._normalize_doc_types(doc_types)
        chunks: list[KnowledgeChunk] = []
        files_by_doc_type: dict[str, int] = {}
        skipped_files = 0
        seen_source_hashes: set[str] = set()
        existing_source_paths: dict[str, str] = {}

        if not rebuild:
            existing_source_paths = self._load_existing_source_paths()
            seen_source_hashes.update(existing_source_paths.values())

        for doc_type in normalized_doc_types:
            doc_chunks, file_count, skipped = self._load_doc_type_chunks(
                doc_type,
                seen_source_hashes=seen_source_hashes,
                existing_source_paths=existing_source_paths,
            )
            chunks.extend(doc_chunks)
            files_by_doc_type[doc_type] = file_count
            skipped_files += skipped

        self._ensure_collection(rebuild=rebuild)
        self._ensure_lexical_index(rebuild=rebuild)
        if chunks:
            self._upsert_chunks(chunks)
            self._upsert_lexical_chunks(chunks)

        chunks_by_doc_type: dict[str, int] = {}
        for chunk in chunks:
            doc_type = str(chunk.payload.get("doc_type", "unknown"))
            chunks_by_doc_type[doc_type] = chunks_by_doc_type.get(doc_type, 0) + 1

        return KnowledgeBuildSummary(
            collection_name=self.settings.knowledge_base.collection_name,
            total_chunks=len(chunks),
            chunks_by_doc_type=chunks_by_doc_type,
            files_by_doc_type=files_by_doc_type,
            skipped_files=skipped_files,
        )

    def search(
        self,
        query: str,
        top_k: int = 5,
        doc_types: Sequence[str] | None = None,
        ticker: str | None = None,
        chunk_roles: Sequence[str] | None = None,
        period_end: str | None = None,
        report_type: str | None = None,
        statement_type: str | None = None,
        expand_neighbors: bool = True,
    ) -> list[KnowledgeSearchHit]:
        """Search the Qdrant knowledge base."""

        if not self._qdrant_available():
            raise RuntimeError(
                "qdrant-client is not installed. Install it before querying the knowledge base."
            ) from QDRANT_IMPORT_ERROR

        self._ensure_collection(rebuild=False)
        self._ensure_lexical_index(rebuild=False)

        query_context = self._parse_query_context(query)
        effective_ticker = ticker or query_context.ticker
        normalized_doc_types = self._normalize_doc_types(doc_types) if doc_types else None
        filing_focused = bool(normalized_doc_types) and all(item == "filing" for item in normalized_doc_types)
        effective_period_end = period_end or query_context.period_end
        if filing_focused and not effective_period_end and query_context.publish_date:
            effective_period_end = query_context.publish_date
        effective_publish_date = None if filing_focused else query_context.publish_date
        effective_report_type = report_type or (query_context.report_type if filing_focused else None)
        effective_statement_type = statement_type or (query_context.statement_type if filing_focused else None)
        search_filter = self._build_filter(
            doc_types=normalized_doc_types,
            ticker=effective_ticker,
            publish_date=effective_publish_date,
            chunk_roles=chunk_roles,
            period_end=effective_period_end,
            report_type=effective_report_type,
            statement_type=effective_statement_type,
        )
        vector_candidates = self._search_vector_candidates(
            query=query_context.normalized_query,
            top_k=max(top_k * 4, 16),
            search_filter=search_filter,
        )
        lexical_candidates = self._search_lexical_candidates(
            query_context=query_context,
            top_k=max(top_k * 4, 16),
            doc_types=normalized_doc_types,
            ticker=effective_ticker,
            chunk_roles=chunk_roles,
            publish_date=effective_publish_date,
            period_end=effective_period_end,
            report_type=effective_report_type,
            statement_type=effective_statement_type,
        )
        merged_candidates = self._merge_candidates(vector_candidates, lexical_candidates)
        reranked_candidates = self._rerank_candidates(merged_candidates, query_context)
        primary_hits = self._select_diverse_primary_hits(reranked_candidates, top_k=top_k)

        if expand_neighbors:
            return self._expand_hits(primary_hits)
        return primary_hits

    def _qdrant_available(self) -> bool:
        return QdrantClient is not None and qdrant_models is not None

    def _build_qdrant_client(self) -> QdrantClient:
        if not self._qdrant_available():
            raise RuntimeError(
                "qdrant-client is not installed. Add qdrant-client to the environment first."
            ) from QDRANT_IMPORT_ERROR

        qdrant_cfg = self.settings.knowledge_base
        if qdrant_cfg.qdrant_url.strip():
            return QdrantClient(url=qdrant_cfg.qdrant_url.strip(), api_key=qdrant_cfg.qdrant_api_key or None)

        ensure_directory(qdrant_cfg.qdrant_path)
        return QdrantClient(path=str(qdrant_cfg.qdrant_path))

    def _load_existing_source_hashes(self) -> set[str]:
        """Load source hashes already present in the collection for incremental dedup."""

        collection_name = self.settings.knowledge_base.collection_name
        client = self.qdrant_client
        if not client.collection_exists(collection_name=collection_name):
            return set()

        existing_hashes: set[str] = set()
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=256,
                offset=offset,
                with_payload=["source_hash"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                source_hash = payload.get("source_hash")
                if source_hash:
                    existing_hashes.add(str(source_hash))
            if offset is None:
                break
        return existing_hashes

    def _load_existing_source_paths(self) -> dict[str, str]:
        """Load source-path to source-hash mapping already present in the collection."""

        collection_name = self.settings.knowledge_base.collection_name
        client = self.qdrant_client
        if not client.collection_exists(collection_name=collection_name):
            return {}

        mapping: dict[str, str] = {}
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=256,
                offset=offset,
                with_payload=["source_path", "source_hash"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                source_path = payload.get("source_path")
                source_hash = payload.get("source_hash")
                if source_path and source_hash:
                    mapping[str(source_path)] = str(source_hash)
            if offset is None:
                break
        return mapping

    def _ensure_collection(self, rebuild: bool = False) -> None:
        client = self.qdrant_client
        collection_name = self.settings.knowledge_base.collection_name
        vector_size = self.embedding_model.get_sentence_embedding_dimension()

        if rebuild and client.collection_exists(collection_name=collection_name):
            client.delete_collection(collection_name=collection_name)

        if client.collection_exists(collection_name=collection_name):
            self._ensure_payload_indexes()
            return

        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(
                size=vector_size,
                distance=qdrant_models.Distance.COSINE,
            ),
        )
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Create useful payload indexes for filtering."""

        client = self.qdrant_client
        collection_name = self.settings.knowledge_base.collection_name
        index_fields = [
            ("doc_type", qdrant_models.PayloadSchemaType.KEYWORD),
            ("corpus_type", qdrant_models.PayloadSchemaType.KEYWORD),
            ("chunk_role", qdrant_models.PayloadSchemaType.KEYWORD),
            ("ticker", qdrant_models.PayloadSchemaType.KEYWORD),
            ("broker", qdrant_models.PayloadSchemaType.KEYWORD),
            ("publish_date", qdrant_models.PayloadSchemaType.KEYWORD),
            ("period_end", qdrant_models.PayloadSchemaType.KEYWORD),
            ("report_type", qdrant_models.PayloadSchemaType.KEYWORD),
            ("statement_type", qdrant_models.PayloadSchemaType.KEYWORD),
            ("issuer", qdrant_models.PayloadSchemaType.KEYWORD),
            ("source_hash", qdrant_models.PayloadSchemaType.KEYWORD),
            ("source_path", qdrant_models.PayloadSchemaType.KEYWORD),
            ("section_path_text", qdrant_models.PayloadSchemaType.KEYWORD),
            ("source_title", qdrant_models.PayloadSchemaType.KEYWORD),
        ]

        for field_name, field_schema in index_fields:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception:
                continue

    def _upsert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        embeddings = self._embed_texts([chunk.content for chunk in chunks])
        points = []
        for chunk, vector in zip(chunks, embeddings, strict=True):
            point_id = self._qdrant_point_id(chunk.id)
            payload = self._stored_chunk_payload(chunk, point_id=point_id)
            points.append(
                qdrant_models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        self.qdrant_client.upsert(
            collection_name=self.settings.knowledge_base.collection_name,
            points=points,
            wait=True,
        )

    def _qdrant_point_id(self, chunk_id: str) -> str:
        """Map readable chunk ids to deterministic UUIDs required by local Qdrant."""

        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"finagent-kb:{chunk_id}"))

    def _stored_chunk_payload(self, chunk: KnowledgeChunk, point_id: str) -> dict[str, Any]:
        payload = dict(chunk.payload)
        payload["content"] = chunk.content
        payload["chunk_id"] = point_id
        payload["source_chunk_id"] = chunk.id
        return payload

    def _delete_chunks_by_source_path(self, source_path: str) -> None:
        """Delete an older document version from Qdrant and the lexical index."""

        collection_name = self.settings.knowledge_base.collection_name
        source_path_value = source_path.strip()
        if not source_path_value:
            return

        if self.qdrant_client.collection_exists(collection_name=collection_name):
            delete_filter = qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="source_path",
                        match=qdrant_models.MatchValue(value=source_path_value),
                    )
                ]
            )
            self.qdrant_client.delete(
                collection_name=collection_name,
                points_selector=qdrant_models.FilterSelector(filter=delete_filter),
                wait=True,
            )

        self._delete_lexical_chunks_by_source_path(source_path_value)

    def _lexical_index_path(self) -> Path:
        return self.settings.knowledge_base.qdrant_path / "kb_lexical_index.sqlite"

    def _ensure_lexical_index(self, rebuild: bool = False) -> None:
        path = self._lexical_index_path()
        ensure_directory(path.parent)
        if rebuild and path.exists():
            path.unlink()

        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    source_hash TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    doc_type TEXT,
                    corpus_type TEXT,
                    chunk_role TEXT,
                    source_title TEXT,
                    ticker TEXT,
                    broker TEXT,
                    publish_date TEXT,
                    publish_date_iso TEXT,
                    period_end TEXT,
                    period_end_iso TEXT,
                    report_type TEXT,
                    statement_type TEXT,
                    issuer TEXT,
                    section_path_text TEXT,
                    content TEXT,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._ensure_sqlite_column(conn, "chunks", "period_end", "TEXT")
            self._ensure_sqlite_column(conn, "chunks", "period_end_iso", "TEXT")
            self._ensure_sqlite_column(conn, "chunks", "report_type", "TEXT")
            self._ensure_sqlite_column(conn, "chunks", "statement_type", "TEXT")
            self._ensure_sqlite_column(conn, "chunks", "issuer", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_hash ON chunks(source_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source_path ON chunks(source_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_type ON chunks(doc_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_ticker ON chunks(ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_broker ON chunks(broker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_chunk_role ON chunks(chunk_role)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_period_end ON chunks(period_end)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_report_type ON chunks(report_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_statement_type ON chunks(statement_type)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_terms (
                    term TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    field TEXT NOT NULL,
                    weight INTEGER NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_terms_term ON chunk_terms(term)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_terms_chunk_id ON chunk_terms(chunk_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_terms_field ON chunk_terms(field)")

    def _ensure_sqlite_column(self, conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        existing_columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            if len(row) > 1
        }
        if column in existing_columns:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _upsert_lexical_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        if not chunks:
            return

        path = self._lexical_index_path()
        self._ensure_lexical_index(rebuild=False)
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            with conn:
                for chunk in chunks:
                    chunk_id = self._qdrant_point_id(chunk.id)
                    payload = self._stored_chunk_payload(chunk, point_id=chunk_id)
                    source_path = str(payload.get("source_path") or "")
                    source_hash = str(payload.get("source_hash") or "")
                    if not source_path or not source_hash:
                        continue

                    content = str(chunk.content)
                    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO chunks (
                            chunk_id,
                            source_hash,
                            source_path,
                            doc_type,
                            corpus_type,
                            chunk_role,
                            source_title,
                            ticker,
                            broker,
                            publish_date,
                            publish_date_iso,
                            period_end,
                            period_end_iso,
                            report_type,
                            statement_type,
                            issuer,
                            section_path_text,
                            content,
                            payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk_id,
                            source_hash,
                            source_path,
                            str(payload.get("doc_type") or ""),
                            str(payload.get("corpus_type") or ""),
                            str(payload.get("chunk_role") or ""),
                            str(payload.get("source_title") or ""),
                            str(payload.get("ticker") or ""),
                            str(payload.get("broker") or ""),
                            str(payload.get("publish_date") or ""),
                            str(payload.get("publish_date_iso") or ""),
                            str(payload.get("period_end") or ""),
                            str(payload.get("period_end_iso") or ""),
                            str(payload.get("report_type") or ""),
                            str(payload.get("statement_type") or ""),
                            str(payload.get("issuer") or ""),
                            str(payload.get("section_path_text") or ""),
                            content,
                            payload_json,
                        ),
                    )
                    conn.execute("DELETE FROM chunk_terms WHERE chunk_id = ?", (chunk_id,))

                    term_rows = self._lexical_term_rows(payload=payload, content=content)
                    if term_rows:
                        conn.executemany(
                            "INSERT INTO chunk_terms (term, chunk_id, field, weight) VALUES (?, ?, ?, ?)",
                            [(term, chunk_id, field, weight) for term, field, weight in term_rows],
                        )

    def _delete_lexical_chunks_by_source_path(self, source_path: str) -> None:
        path = self._lexical_index_path()
        if not path.exists():
            return

        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT chunk_id FROM chunks WHERE source_path = ?", (source_path,)).fetchall()
            chunk_ids = [str(row[0]) for row in rows if row and row[0]]
            with conn:
                if chunk_ids:
                    conn.executemany("DELETE FROM chunk_terms WHERE chunk_id = ?", ((chunk_id,) for chunk_id in chunk_ids))
                    conn.executemany("DELETE FROM chunks WHERE chunk_id = ?", ((chunk_id,) for chunk_id in chunk_ids))

    def _lexical_term_rows(self, payload: dict[str, Any], content: str) -> list[tuple[str, str, int]]:
        rows: list[tuple[str, str, int]] = []
        seen: set[tuple[str, str]] = set()

        field_specs = [
            ("source_title", payload.get("source_title"), 4, 80),
            ("section_path_text", payload.get("section_path_text"), 3, 80),
            ("metadata", payload.get("ticker"), 5, 20),
            ("metadata", payload.get("broker"), 4, 20),
            ("metadata", payload.get("publish_date_iso") or payload.get("publish_date"), 3, 20),
            ("metadata", payload.get("period_end_iso") or payload.get("period_end"), 5, 20),
            ("metadata", payload.get("report_type"), 4, 20),
            ("metadata", payload.get("statement_type"), 4, 20),
            ("metadata", payload.get("issuer"), 3, 30),
            ("metadata", payload.get("doc_type"), 2, 20),
            ("metadata", payload.get("corpus_type"), 2, 20),
            ("content", content, 1, 160),
        ]

        for field, text, weight, limit in field_specs:
            for term in self._extract_search_terms(str(text or ""), max_terms=limit):
                key = (field, term)
                if key in seen:
                    continue
                seen.add(key)
                rows.append((term, field, weight))
        return rows

    def _embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self.embedding_model.encode(
            list(texts),
            batch_size=self.settings.knowledge_base.embedding_batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return [list(row) for row in embeddings]

    def _search_vector_candidates(
        self,
        query: str,
        top_k: int,
        search_filter: Any | None = None,
    ) -> list[KnowledgeSearchHit]:
        if not query.strip():
            return []

        query_vector = self._embed_texts([query])[0]
        client = self.qdrant_client
        if hasattr(client, "search"):
            results = client.search(
                collection_name=self.settings.knowledge_base.collection_name,
                query_vector=query_vector,
                limit=top_k,
                query_filter=search_filter,
                with_payload=True,
                with_vectors=False,
            )
        else:
            query_response = client.query_points(
                collection_name=self.settings.knowledge_base.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=search_filter,
                with_payload=True,
                with_vectors=False,
            )
            results = getattr(query_response, "points", query_response)

        hits: list[KnowledgeSearchHit] = []
        for point in results:
            payload = dict(point.payload or {})
            hits.append(
                KnowledgeSearchHit(
                    id=str(point.id),
                    score=float(point.score or 0.0),
                    content=str(payload.get("content", "")),
                    payload=payload,
                )
            )
        return hits

    def _search_lexical_candidates(
        self,
        query_context: KnowledgeQueryContext,
        top_k: int,
        doc_types: Sequence[str] | None = None,
        ticker: str | None = None,
        chunk_roles: Sequence[str] | None = None,
        publish_date: str | None = None,
        period_end: str | None = None,
        report_type: str | None = None,
        statement_type: str | None = None,
    ) -> list[KnowledgeSearchHit]:
        path = self._lexical_index_path()
        if not path.exists():
            return []

        normalized_terms = self._extract_search_terms(query_context.normalized_query, max_terms=24)
        normalized_terms.extend(term for term in query_context.search_terms if term not in normalized_terms)
        if query_context.ticker:
            normalized_terms.extend(self._extract_search_terms(query_context.ticker, max_terms=4))
            normalized_terms.append(query_context.ticker.strip().upper())
        if query_context.publish_date:
            normalized_terms.extend(self._normalize_date_candidates(query_context.publish_date))
        if query_context.period_end:
            normalized_terms.extend(self._normalize_date_candidates(query_context.period_end))
        if query_context.report_type:
            normalized_terms.extend(self._extract_search_terms(query_context.report_type, max_terms=4))
        if query_context.statement_type:
            normalized_terms.extend(self._extract_search_terms(query_context.statement_type, max_terms=4))

        terms = self._deduplicate_terms(normalized_terms)
        if not terms:
            return []

        params: list[Any] = []
        where_clauses: list[str] = []
        term_placeholders = ", ".join("?" for _ in terms)
        where_clauses.append(f"ct.term IN ({term_placeholders})")
        params.extend(terms)

        if doc_types:
            normalized_doc_types = self._normalize_doc_types(doc_types)
            if normalized_doc_types:
                doc_type_placeholders = ", ".join("?" for _ in normalized_doc_types)
                where_clauses.append(f"c.doc_type IN ({doc_type_placeholders})")
                params.extend(normalized_doc_types)

        if ticker:
            where_clauses.append("UPPER(c.ticker) = ?")
            params.append(ticker.strip().upper())

        if chunk_roles:
            normalized_roles = [str(item).strip().lower() for item in chunk_roles if str(item).strip()]
            if normalized_roles:
                role_placeholders = ", ".join("?" for _ in normalized_roles)
                where_clauses.append(f"LOWER(c.chunk_role) IN ({role_placeholders})")
                params.extend(normalized_roles)

        date_values = self._normalize_date_candidates(publish_date)
        if date_values:
            date_placeholders = ", ".join("?" for _ in date_values)
            where_clauses.append(f"(c.publish_date IN ({date_placeholders}) OR c.publish_date_iso IN ({date_placeholders}))")
            params.extend(date_values)
            params.extend(date_values)

        period_values = self._normalize_date_candidates(period_end)
        if period_values:
            period_placeholders = ", ".join("?" for _ in period_values)
            where_clauses.append(f"(c.period_end IN ({period_placeholders}) OR c.period_end_iso IN ({period_placeholders}))")
            params.extend(period_values)
            params.extend(period_values)

        if report_type:
            where_clauses.append("LOWER(c.report_type) = ?")
            params.append(self._normalize_report_type(report_type) or str(report_type).strip().lower())

        if statement_type:
            where_clauses.append("LOWER(c.statement_type) = ?")
            params.append(self._normalize_statement_type(statement_type) or str(statement_type).strip().lower())

        limit = max(top_k * 8, 32)
        params.append(limit)
        query_sql = f"""
            SELECT
                c.chunk_id,
                c.content,
                c.payload_json,
                SUM(ct.weight) AS weighted_score,
                COUNT(DISTINCT ct.term) AS match_count
            FROM chunk_terms ct
            JOIN chunks c ON c.chunk_id = ct.chunk_id
            WHERE {" AND ".join(where_clauses)}
            GROUP BY c.chunk_id
            ORDER BY weighted_score DESC, match_count DESC
            LIMIT ?
        """

        path = self._lexical_index_path()
        hits: list[KnowledgeSearchHit] = []
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query_sql, params).fetchall()
            for row in rows:
                payload_json = str(row["payload_json"] or "{}")
                try:
                    payload = json.loads(payload_json)
                except json.JSONDecodeError:
                    payload = {}
                hits.append(
                    KnowledgeSearchHit(
                        id=str(row["chunk_id"]),
                        score=float(row["weighted_score"] or 0.0),
                        content=str(row["content"] or payload.get("content", "")),
                        payload=payload,
                    )
                )
        return hits

    def _merge_candidates(
        self,
        vector_candidates: list[KnowledgeSearchHit],
        lexical_candidates: list[KnowledgeSearchHit],
    ) -> list[KnowledgeSearchCandidate]:
        merged: dict[str, dict[str, Any]] = {}

        for rank, hit in enumerate(vector_candidates):
            entry = merged.setdefault(
                hit.id,
                {
                    "hit": hit,
                    "vector_rank": None,
                    "lexical_rank": None,
                    "vector_score": 0.0,
                    "lexical_score": 0.0,
                },
            )
            entry["vector_rank"] = rank
            entry["vector_score"] = hit.score
            if entry["hit"].score < hit.score:
                entry["hit"] = hit

        for rank, hit in enumerate(lexical_candidates):
            entry = merged.setdefault(
                hit.id,
                {
                    "hit": hit,
                    "vector_rank": None,
                    "lexical_rank": None,
                    "vector_score": 0.0,
                    "lexical_score": 0.0,
                },
            )
            entry["lexical_rank"] = rank
            entry["lexical_score"] = hit.score
            if entry["hit"].score < hit.score:
                entry["hit"] = hit

        candidates: list[KnowledgeSearchCandidate] = []
        for entry in merged.values():
            fused_score = 0.0
            if entry["vector_rank"] is not None:
                fused_score += 1.0 / (60.0 + float(entry["vector_rank"]) + 1.0)
            if entry["lexical_rank"] is not None:
                fused_score += 1.0 / (60.0 + float(entry["lexical_rank"]) + 1.0)

            hit = entry["hit"]
            payload = dict(hit.payload)
            payload["vector_score"] = entry["vector_score"]
            payload["lexical_score"] = entry["lexical_score"]
            payload["fused_score"] = fused_score
            candidates.append(
                KnowledgeSearchCandidate(
                    hit=KnowledgeSearchHit(
                        id=hit.id,
                        score=fused_score,
                        content=hit.content,
                        payload=payload,
                    ),
                    vector_score=float(entry["vector_score"]),
                    lexical_score=float(entry["lexical_score"]),
                    fused_score=fused_score,
                )
            )

        candidates.sort(key=lambda item: item.fused_score, reverse=True)
        return candidates

    def _rerank_candidates(
        self,
        candidates: list[KnowledgeSearchCandidate],
        query_context: KnowledgeQueryContext,
    ) -> list[KnowledgeSearchCandidate]:
        reranked: list[KnowledgeSearchCandidate] = []
        query_terms = query_context.search_terms
        query_title = query_context.normalized_query.lower()

        for candidate in candidates:
            payload = dict(candidate.hit.payload)
            title = str(payload.get("source_title") or "")
            section_path_text = str(payload.get("section_path_text") or "")
            content = candidate.hit.content
            score = float(candidate.fused_score)

            chunk_role = str(payload.get("chunk_role") or "").lower()
            if chunk_role == "evidence":
                score += 0.05
            elif chunk_role == "summary":
                score -= 0.02

            ticker = query_context.ticker
            if ticker and str(payload.get("ticker") or "").upper() == ticker.upper():
                score += 0.2

            publish_date = query_context.publish_date
            if publish_date and self._payload_matches_date(payload, publish_date):
                score += 0.1

            period_end = query_context.period_end
            if period_end and self._payload_matches_period_end(payload, period_end):
                score += 0.15

            report_type = query_context.report_type
            if report_type and str(payload.get("report_type") or "").lower() == report_type.lower():
                score += 0.08

            statement_type = query_context.statement_type
            if statement_type and str(payload.get("statement_type") or "").lower() == statement_type.lower():
                score += 0.08

            if query_title and query_title in title.lower():
                score += 0.08
            if query_title and query_title in section_path_text.lower():
                score += 0.05

            if query_terms:
                lower_title = title.lower()
                lower_section = section_path_text.lower()
                lower_content = content.lower()
                title_hits = sum(1 for term in query_terms if term in lower_title)
                section_hits = sum(1 for term in query_terms if term in lower_section)
                content_hits = sum(1 for term in query_terms if term in lower_content)
                score += min(0.08 * title_hits + 0.05 * section_hits + 0.01 * content_hits, 0.25)

            payload["vector_score"] = candidate.vector_score
            payload["lexical_score"] = candidate.lexical_score
            payload["fused_score"] = candidate.fused_score
            payload["rerank_score"] = score
            reranked.append(
                KnowledgeSearchCandidate(
                    hit=KnowledgeSearchHit(
                        id=candidate.hit.id,
                        score=score,
                        content=candidate.hit.content,
                        payload=payload,
                    ),
                    vector_score=candidate.vector_score,
                    lexical_score=candidate.lexical_score,
                    fused_score=score,
                )
            )

        reranked.sort(key=lambda item: item.fused_score, reverse=True)
        return reranked

    def _select_diverse_primary_hits(
        self,
        candidates: list[KnowledgeSearchCandidate],
        top_k: int,
    ) -> list[KnowledgeSearchHit]:
        """Select at most top_k hits while avoiding duplicate paragraph contexts."""

        if top_k <= 0 or not candidates:
            return []

        top_score = float(candidates[0].hit.score)
        score_floor = top_score * RERANK_DEDUP_SCORE_RATIO if top_score > 0 else top_score
        selected: list[KnowledgeSearchHit] = []
        seen_contexts: set[tuple[Any, ...]] = set()

        for candidate in candidates:
            score = float(candidate.hit.score)
            if selected and score < score_floor:
                break

            context_key = self._hit_context_key(candidate.hit)
            if context_key in seen_contexts:
                continue

            payload = dict(candidate.hit.payload)
            payload["selection_score_floor"] = score_floor
            payload["selection_score_ratio"] = RERANK_DEDUP_SCORE_RATIO
            payload["selection_context_key"] = "|".join(str(item) for item in context_key)
            selected.append(
                KnowledgeSearchHit(
                    id=candidate.hit.id,
                    score=candidate.hit.score,
                    content=candidate.hit.content,
                    payload=payload,
                )
            )
            seen_contexts.add(context_key)
            if len(selected) >= top_k:
                break

        return selected

    def _hit_context_key(self, hit: KnowledgeSearchHit) -> tuple[Any, ...]:
        payload = hit.payload
        paragraph_index = self._optional_int(payload.get("paragraph_index"))
        if paragraph_index is None:
            return ("chunk", hit.id)

        source_key = str(payload.get("source_hash") or payload.get("source_path") or "")
        return (
            "paragraph",
            source_key,
            self._payload_key_text(payload, "page_start"),
            self._payload_key_text(payload, "page_end"),
            self._payload_key_text(payload, "section_index"),
            self._payload_key_text(payload, "section_path_text"),
            paragraph_index,
        )

    def _expand_hits(self, hits: list[KnowledgeSearchHit], neighbor_window: int = 1) -> list[KnowledgeSearchHit]:
        if not hits:
            return []

        cache: dict[str, list[KnowledgeSearchHit]] = {}
        expanded: list[KnowledgeSearchHit] = []
        for hit in hits:
            source_hash = str(hit.payload.get("source_hash") or "")
            if not source_hash:
                expanded.append(hit)
                continue

            if source_hash not in cache:
                cache[source_hash] = self._load_document_chunks(source_hash)

            expanded.append(self._expand_hit_with_neighbors(hit, cache[source_hash], neighbor_window=neighbor_window))
        return expanded

    def _normalize_doc_types(self, doc_types: Sequence[str] | None) -> list[str]:
        allowed = ["report", "filing", "encyclopedia", "glossary"]
        aliases = {
            "research_report": "report",
            "reports": "report",
            "filings": "filing",
            "financial_filing": "filing",
            "financial_filings": "filing",
            "financial_report": "filing",
            "financial_reports": "filing",
            "annual_report": "filing",
        }
        if not doc_types:
            return allowed

        normalized: list[str] = []
        seen: set[str] = set()
        for item in doc_types:
            doc_type = str(item).strip().lower()
            if not doc_type:
                continue
            doc_type = aliases.get(doc_type, doc_type)
            if doc_type not in allowed:
                raise ValueError(f"Unsupported doc type: {doc_type}")
            if doc_type in seen:
                continue
            seen.add(doc_type)
            normalized.append(doc_type)
        return normalized or allowed

    def _load_doc_type_chunks(
        self,
        doc_type: str,
        seen_source_hashes: set[str] | None = None,
        existing_source_paths: dict[str, str] | None = None,
    ) -> tuple[list[KnowledgeChunk], int, int]:
        root = self._root_for_doc_type(doc_type)
        if not root.exists():
            return [], 0, 0

        chunks: list[KnowledgeChunk] = []
        file_count = 0
        skipped_files = 0

        for path in sorted(root.rglob("*")):
            if not path.is_file() or self._should_skip_file(path):
                continue
            supported_extensions = self._supported_extensions_for_doc_type(doc_type)
            if supported_extensions and path.suffix.lower() not in supported_extensions:
                skipped_files += 1
                continue

            file_count += 1
            try:
                source_hash = self._file_sha256(path)
                source_path = self._relative_path(path)
                previous_hash = existing_source_paths.get(source_path) if existing_source_paths else None

                if previous_hash == source_hash:
                    skipped_files += 1
                    continue

                if seen_source_hashes is not None and source_hash in seen_source_hashes:
                    skipped_files += 1
                    continue

                if doc_type == "report":
                    file_chunks = self._chunk_report_file(path, source_hash=source_hash)
                elif doc_type == "filing":
                    file_chunks = self._chunk_filing_file(path, source_hash=source_hash)
                elif doc_type == "encyclopedia":
                    file_chunks = self._chunk_encyclopedia_file(path, source_hash=source_hash)
                elif doc_type == "glossary":
                    file_chunks = self._chunk_glossary_file(path, source_hash=source_hash)
                else:  # pragma: no cover - guarded by normalization
                    raise ValueError(f"Unsupported doc type: {doc_type}")

                if previous_hash and previous_hash != source_hash:
                    self._delete_chunks_by_source_path(source_path)

                if seen_source_hashes is not None:
                    seen_source_hashes.add(source_hash)
                if existing_source_paths is not None:
                    existing_source_paths[source_path] = source_hash

                chunks.extend(file_chunks)
            except Exception:
                skipped_files += 1
                continue

        return chunks, file_count, skipped_files

    def _root_for_doc_type(self, doc_type: str) -> Path:
        kb = self.settings.knowledge_base
        if doc_type == "report":
            return kb.raw_reports_dir
        if doc_type == "filing":
            return kb.raw_filings_dir
        if doc_type == "encyclopedia":
            return kb.raw_encyclopedia_dir
        if doc_type == "glossary":
            return kb.raw_glossary_dir
        raise ValueError(f"Unsupported doc type: {doc_type}")

    def _supported_extensions_for_doc_type(self, doc_type: str) -> set[str]:
        if doc_type == "report":
            return SUPPORTED_REPORT_EXTENSIONS
        if doc_type == "filing":
            return SUPPORTED_FILING_EXTENSIONS
        if doc_type == "encyclopedia":
            return SUPPORTED_ENCYCLOPEDIA_EXTENSIONS
        if doc_type == "glossary":
            return SUPPORTED_GLOSSARY_EXTENSIONS
        return set()

    def _should_skip_file(self, path: Path) -> bool:
        name = path.name.lower()
        return (
            name.startswith(".")
            or name.startswith("readme")
            or "template" in name
            or name.endswith(".tmp")
        )

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _chunk_report_file(self, path: Path, source_hash: str) -> list[KnowledgeChunk]:
        suffix = path.suffix.lower()
        metadata = self._parse_report_filename(path.stem)
        metadata.update(
            {
                "doc_type": "report",
                "corpus_type": "research_report",
                "source_type": "report",
                "source_path": self._relative_path(path),
                "file_name": path.name,
                "source_title": metadata.get("subject") or path.stem,
                "source_hash": source_hash,
            }
        )

        if suffix == ".pdf":
            return self._chunk_pdf(
                path,
                metadata,
                max_tokens=self.settings.knowledge_base.report_chunk_tokens,
                overlap=self.settings.knowledge_base.report_chunk_overlap,
                include_summary=True,
            )
        if suffix in {".md", ".markdown", ".txt"}:
            text = self._read_text_file(path)
            return self._chunk_structured_text(
                path=path,
                text=text,
                metadata=metadata,
                doc_type="report",
                max_tokens=self.settings.knowledge_base.report_chunk_tokens,
                overlap=self.settings.knowledge_base.report_chunk_overlap,
                default_title=metadata["source_title"],
                include_summary=True,
            )
        return []

    def _chunk_filing_file(self, path: Path, source_hash: str) -> list[KnowledgeChunk]:
        suffix = path.suffix.lower()
        metadata = self._parse_filing_filename(path.stem)
        metadata.update(
            {
                "doc_type": "filing",
                "corpus_type": "financial_filing",
                "source_type": "filing",
                "source_path": self._relative_path(path),
                "file_name": path.name,
                "source_hash": source_hash,
            }
        )
        metadata["source_title"] = metadata.get("source_title") or path.stem

        if suffix == ".pdf":
            return self._chunk_pdf(
                path,
                metadata,
                max_tokens=self.settings.knowledge_base.filing_chunk_tokens,
                overlap=self.settings.knowledge_base.filing_chunk_overlap,
                include_summary=True,
            )

        if suffix in {".md", ".markdown", ".txt"}:
            text = self._read_text_file(path)
        elif suffix in {".html", ".htm", ".xhtml", ".xml"}:
            text = self._read_markup_file(path)
        elif suffix == ".csv":
            text = self._read_filing_csv_text(path)
        elif suffix == ".json":
            text = self._read_filing_json_text(path)
        else:
            return []

        return self._chunk_structured_text(
            path=path,
            text=text,
            metadata=metadata,
            doc_type="filing",
            max_tokens=self.settings.knowledge_base.filing_chunk_tokens,
            overlap=self.settings.knowledge_base.filing_chunk_overlap,
            default_title=metadata["source_title"],
            include_summary=True,
        )

    def _chunk_encyclopedia_file(self, path: Path, source_hash: str) -> list[KnowledgeChunk]:
        suffix = path.suffix.lower()
        metadata = {
            "doc_type": "encyclopedia",
            "corpus_type": "encyclopedia",
            "source_type": "encyclopedia",
            "source_path": self._relative_path(path),
            "file_name": path.name,
            "source_title": path.stem,
            "source_hash": source_hash,
        }

        if suffix == ".pdf":
            return self._chunk_pdf(
                path,
                metadata,
                max_tokens=self.settings.knowledge_base.encyclopedia_chunk_tokens,
                overlap=self.settings.knowledge_base.encyclopedia_chunk_overlap,
                include_summary=False,
            )
        if suffix in {".md", ".markdown", ".txt"}:
            text = self._read_text_file(path)
            return self._chunk_structured_text(
                path=path,
                text=text,
                metadata=metadata,
                doc_type="encyclopedia",
                max_tokens=self.settings.knowledge_base.encyclopedia_chunk_tokens,
                overlap=self.settings.knowledge_base.encyclopedia_chunk_overlap,
                default_title=path.stem,
                include_summary=False,
            )
        return []

    def _chunk_glossary_file(self, path: Path, source_hash: str) -> list[KnowledgeChunk]:
        suffix = path.suffix.lower()
        metadata = {
            "doc_type": "glossary",
            "corpus_type": "glossary",
            "source_type": "glossary",
            "source_path": self._relative_path(path),
            "file_name": path.name,
            "source_title": path.stem,
            "source_hash": source_hash,
        }

        if suffix == ".csv":
            rows = self._read_csv_rows(path)
            return self._chunk_glossary_rows(rows, metadata, source_path=path)

        if suffix in {".json"}:
            rows = self._read_json_rows(path)
            return self._chunk_glossary_rows(rows, metadata, source_path=path)

        if suffix in {".yaml", ".yml"}:
            rows = self._read_yaml_rows(path)
            return self._chunk_glossary_rows(rows, metadata, source_path=path)

        if suffix in {".md", ".markdown", ".txt"}:
            text = self._read_text_file(path)
            entries = self._parse_glossary_markdown_entries(text, fallback_term=path.stem)
            return self._chunk_glossary_entries(entries, metadata, source_path=path)

        return []

    def _chunk_pdf(
        self,
        path: Path,
        metadata: dict[str, Any],
        max_tokens: int,
        overlap: int,
        include_summary: bool = False,
    ) -> list[KnowledgeChunk]:
        reader = PdfReader(str(path))
        chunks: list[KnowledgeChunk] = []
        summary_bits: list[str] = []

        for page_index, page in enumerate(reader.pages, start=1):
            page_text = self._normalize_text(page.extract_text() or "")
            if not page_text.strip():
                continue

            page_sections = self._split_sections(page_text, default_title=f"page-{page_index}")
            if not page_sections:
                page_sections = [([f"page-{page_index}"], page_text)]

            for section_index, (section_path, section_text) in enumerate(page_sections):
                section_text = self._normalize_text(section_text)
                if not section_text.strip():
                    continue

                section_path_text = " > ".join(str(item) for item in section_path)
                section_metadata = dict(metadata)
                section_metadata.update(
                    {
                        "page_start": page_index,
                        "page_end": page_index,
                        "section_path": section_path,
                        "section_path_text": section_path_text,
                        "section_title": section_path[-1],
                        "section_depth": len(section_path),
                        "section_index": section_index,
                        "chunk_strategy": "pdf_section_structure_aware",
                        "chunk_role": "evidence",
                    }
                )
                self._apply_filing_section_metadata(section_metadata, section_path_text, section_text)

                if include_summary and len(summary_bits) < REPORT_SUMMARY_PREVIEW_LIMIT:
                    preview = self._section_summary_source(section_path_text, section_text)
                    if preview:
                        summary_bits.append(preview)

                token_chunks = self._split_text_chunks(section_text, max_tokens=max_tokens, overlap=overlap)
                if not token_chunks:
                    continue

                for chunk_index, text_chunk in enumerate(token_chunks):
                    chunk_payload = dict(section_metadata)
                    chunk_payload["chunk_index"] = chunk_index
                    chunk_payload["chunk_total"] = len(token_chunks)
                    self._apply_text_chunk_metadata(chunk_payload, text_chunk)
                    chunk_payload["content"] = self._compose_chunk_text(
                        metadata=chunk_payload,
                        chunk_text=text_chunk.text,
                        title=section_path_text,
                    )
                    chunks.append(
                        KnowledgeChunk(
                            id=self._make_chunk_id(path, f"page-{page_index}-section-{section_index}", chunk_index),
                            content=chunk_payload["content"],
                            payload=chunk_payload,
                        )
                    )

        if include_summary:
            summary_chunk = self._build_report_summary_chunk(path, metadata, summary_bits)
            if summary_chunk is not None:
                chunks.insert(0, summary_chunk)

        return chunks

    def _chunk_structured_text(
        self,
        path: Path,
        text: str,
        metadata: dict[str, Any],
        doc_type: str,
        max_tokens: int,
        overlap: int,
        default_title: str,
        include_summary: bool = False,
    ) -> list[KnowledgeChunk]:
        sections = self._split_sections(text, default_title=default_title)
        if not sections:
            sections = [([default_title], text)]

        chunks: list[KnowledgeChunk] = []
        summary_bits: list[str] = []
        for section_index, (section_path, section_text) in enumerate(sections):
            section_text = self._normalize_text(section_text)
            if not section_text.strip():
                continue

            section_path_text = " > ".join(str(item) for item in section_path)
            section_payload = dict(metadata)
            section_payload.update(
                {
                    "doc_type": doc_type,
                    "section_path": section_path,
                    "section_path_text": section_path_text,
                    "section_title": section_path[-1],
                    "section_depth": len(section_path),
                    "section_index": section_index,
                    "chunk_strategy": "markdown_section_structure_aware" if doc_type != "glossary" else "glossary_text_structure_aware",
                    "chunk_role": "evidence",
                }
            )
            self._apply_filing_section_metadata(section_payload, section_path_text, section_text)

            if include_summary and len(summary_bits) < REPORT_SUMMARY_PREVIEW_LIMIT:
                preview = self._section_summary_source(section_path_text, section_text)
                if preview:
                    summary_bits.append(preview)

            token_chunks = self._split_text_chunks(section_text, max_tokens=max_tokens, overlap=overlap)
            if not token_chunks:
                continue

            for chunk_index, text_chunk in enumerate(token_chunks):
                payload = dict(section_payload)
                payload["chunk_index"] = chunk_index
                payload["chunk_total"] = len(token_chunks)
                self._apply_text_chunk_metadata(payload, text_chunk)
                rendered_content = self._compose_chunk_text(
                    metadata=payload,
                    chunk_text=text_chunk.text,
                    title=section_path_text,
                )
                payload["content"] = rendered_content
                chunks.append(
                    KnowledgeChunk(
                        id=self._make_chunk_id(path, section_index, chunk_index),
                        content=rendered_content,
                        payload=payload,
                    )
                )

        if include_summary:
            summary_chunk = self._build_report_summary_chunk(path, metadata, summary_bits)
            if summary_chunk is not None:
                chunks.insert(0, summary_chunk)
        return chunks

    def _chunk_glossary_rows(
        self,
        rows: list[dict[str, Any]],
        metadata: dict[str, Any],
        source_path: Path,
    ) -> list[KnowledgeChunk]:
        entries: list[tuple[str, dict[str, Any]]] = []
        for row in rows:
            term = self._extract_glossary_term(row)
            if not term:
                continue
            entries.append((term, row))
        return self._chunk_glossary_entries(entries, metadata, source_path=source_path)

    def _split_sections(self, text: str, default_title: str) -> list[tuple[list[str], str]]:
        lines = self._normalize_text(text).splitlines()
        sections: list[tuple[list[str], str]] = []
        stack: list[tuple[int, str]] = []
        current_lines: list[str] = []

        def current_path() -> list[str]:
            return [default_title] + [title for _, title in stack]

        def flush() -> None:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append((current_path(), body))

        for line in lines:
            heading = self._parse_heading_line(line.strip())
            if heading is not None:
                flush()
                current_lines = []
                level, title = heading
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                continue
            current_lines.append(line)

        flush()

        if not sections:
            stripped = "\n".join(lines).strip()
            if stripped:
                sections.append(([default_title], stripped))

        return sections

    def _split_markdown_sections(self, text: str, default_title: str) -> list[tuple[list[str], str]]:
        return self._split_sections(text, default_title)

    def _parse_heading_line(self, line: str) -> tuple[int, str] | None:
        if not line:
            return None

        markdown_match = HEADING_PATTERN.match(line)
        if markdown_match:
            return len(markdown_match.group(1)), markdown_match.group(2).strip()

        chapter_match = CHINESE_CHAPTER_PATTERN.match(line)
        if chapter_match:
            title = line.strip()
            if len(title) <= 120:
                return 1, title

        outline_match = CHINESE_OUTLINE_PATTERN.match(line)
        if outline_match:
            title = line.strip()
            if len(title) <= 120:
                level = 2 if "." not in outline_match.group(1) else min(4, outline_match.group(1).count(".") + 2)
                return level, title

        suboutline_match = CHINESE_SUBOUTLINE_PATTERN.match(line)
        if suboutline_match:
            title = line.strip()
            if len(title) <= 120:
                return 3, title

        arabic_match = ARABIC_OUTLINE_PATTERN.match(line)
        if arabic_match:
            title = line.strip()
            if len(title) <= 120:
                level = min(5, arabic_match.group(1).count(".") + 2)
                return level, title

        return None

    def _split_token_chunks(self, text: str, max_tokens: int, overlap: int) -> list[str]:
        return [chunk.text for chunk in self._split_text_chunks(text, max_tokens=max_tokens, overlap=overlap)]

    def _split_text_chunks(self, text: str, max_tokens: int, overlap: int) -> list[TextChunk]:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= max_tokens:
            raise ValueError("overlap must be smaller than max_tokens")

        normalized_text = self._normalize_text(text)
        if not normalized_text:
            return []

        chunks: list[TextChunk] = []
        for paragraph_index, paragraph in enumerate(self._split_paragraph_units(normalized_text)):
            sentence_units = self._split_sentence_units(paragraph)
            if not sentence_units:
                continue

            paragraph_chunks: list[str] = []
            for start in range(0, len(sentence_units), 2):
                chunk_text = self._join_sentence_parts(sentence_units[start : start + 2])
                if not chunk_text:
                    continue
                if self._token_count(chunk_text) <= max_tokens:
                    paragraph_chunks.append(chunk_text)
                    continue
                paragraph_chunks.extend(
                    self._split_by_token_window(
                        chunk_text,
                        max_tokens=max_tokens,
                        overlap=overlap,
                    )
                )

            paragraph_token_count = self._token_count(paragraph)
            paragraph_chunk_total = len(paragraph_chunks)
            for paragraph_chunk_index, chunk_text in enumerate(paragraph_chunks):
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        token_count=self._token_count(chunk_text),
                        paragraph_index=paragraph_index,
                        paragraph_chunk_index=paragraph_chunk_index,
                        paragraph_chunk_total=paragraph_chunk_total,
                        paragraph_token_count=paragraph_token_count,
                    )
                )
        return chunks

    def _apply_text_chunk_metadata(self, payload: dict[str, Any], text_chunk: TextChunk) -> None:
        payload["chunk_text"] = text_chunk.text
        payload["token_count"] = text_chunk.token_count
        payload["paragraph_index"] = text_chunk.paragraph_index
        payload["paragraph_chunk_index"] = text_chunk.paragraph_chunk_index
        payload["paragraph_chunk_total"] = text_chunk.paragraph_chunk_total
        payload["paragraph_token_count"] = text_chunk.paragraph_token_count

    def _split_paragraph_units(self, text: str) -> list[str]:
        """Split text into paragraph-like units before token fallback."""

        paragraphs = [
            self._normalize_text(part)
            for part in re.split(r"\n\s*\n+", self._normalize_text(text))
            if self._normalize_text(part)
        ]
        return paragraphs or [self._normalize_text(text)]

    def _split_sentence_units(self, text: str) -> list[str]:
        normalized_text = self._normalize_text(text)
        if not normalized_text:
            return []

        sentences = re.split(
            r"(?<=[。！？!?；;])\s*|(?<=[.!?;])\s+(?=[A-Z0-9\"'“‘(])",
            normalized_text,
        )
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _split_by_token_window(self, text: str, max_tokens: int, overlap: int) -> list[str]:
        tokens = self._encoding.encode(self._normalize_text(text))
        if not tokens:
            return []

        chunks: list[str] = []
        step = max_tokens - overlap if overlap > 0 else max_tokens
        for start in range(0, len(tokens), step):
            chunk_tokens = tokens[start : start + max_tokens]
            if not chunk_tokens:
                continue
            chunk_text = self._encoding.decode(chunk_tokens).strip()
            if chunk_text:
                chunks.append(chunk_text)
            if start + max_tokens >= len(tokens):
                break
        return chunks

    def _token_count(self, text: str) -> int:
        return len(self._encoding.encode(self._normalize_text(text)))

    def _join_chunk_parts(self, parts: Sequence[str]) -> str:
        return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip()

    def _join_sentence_parts(self, parts: Sequence[str]) -> str:
        return " ".join(part.strip() for part in parts if part and part.strip()).strip()

    def _apply_filing_section_metadata(
        self,
        metadata: dict[str, Any],
        section_path_text: str,
        section_text: str,
    ) -> None:
        if metadata.get("doc_type") != "filing":
            return

        metadata["chunk_strategy"] = str(metadata.get("chunk_strategy") or "").replace(
            "pdf_section_structure_aware",
            "filing_pdf_section_structure_aware",
        ).replace(
            "markdown_section_structure_aware",
            "filing_section_structure_aware",
        ).replace(
            "pdf_section_token_window",
            "filing_pdf_section_token_window",
        ).replace(
            "markdown_section_token_window",
            "filing_section_token_window",
        )
        statement_type = metadata.get("statement_type") or self._infer_statement_type(
            f"{section_path_text}\n{section_text[:1200]}"
        )
        if statement_type:
            metadata["statement_type"] = statement_type

    def _compose_chunk_text(self, metadata: dict[str, Any], chunk_text: str, title: str) -> str:
        content_lines = [f"标题: {title}"]
        doc_type = metadata.get("doc_type")
        if doc_type:
            content_lines.append(f"文档类型: {doc_type}")

        if metadata.get("ticker"):
            content_lines.append(f"Ticker: {metadata['ticker']}")
        if metadata.get("publish_date"):
            content_lines.append(f"发布日期: {metadata['publish_date']}")
        if metadata.get("period_end"):
            content_lines.append(f"报告期: {metadata['period_end']}")
        if metadata.get("report_type"):
            content_lines.append(f"报告类型: {metadata['report_type']}")
        if metadata.get("statement_type"):
            content_lines.append(f"报表/章节类型: {metadata['statement_type']}")
        if metadata.get("issuer"):
            content_lines.append(f"主体: {metadata['issuer']}")
        if metadata.get("broker"):
            content_lines.append(f"机构: {metadata['broker']}")
        if metadata.get("term"):
            content_lines.append(f"术语: {metadata['term']}")
        if metadata.get("section_path_text"):
            content_lines.append(f"章节路径: {metadata['section_path_text']}")
        elif metadata.get("section_path"):
            section_path = metadata["section_path"]
            if isinstance(section_path, list):
                content_lines.append(f"章节路径: {' > '.join(str(item) for item in section_path)}")
            else:
                content_lines.append(f"章节路径: {section_path}")

        content_lines.append("")
        content_lines.append(chunk_text.strip())
        return "\n".join(content_lines).strip()

    def _parse_report_filename(self, stem: str) -> dict[str, Any]:
        parts = stem.split("_")
        metadata: dict[str, Any] = {
            "ticker": "UNKNOWN",
            "publish_date": "UNKNOWN",
            "broker": "UNKNOWN",
            "subject": stem,
        }

        date_index = -1
        for index, part in enumerate(parts):
            if part.isdigit() and len(part) == 8:
                date_index = index
                break

        if date_index != -1:
            metadata["ticker"] = parts[0]
            metadata["publish_date"] = parts[date_index]
            if re.fullmatch(r"\d{8}", metadata["publish_date"]):
                metadata["publish_date_iso"] = (
                    f"{metadata['publish_date'][:4]}-{metadata['publish_date'][4:6]}-{metadata['publish_date'][6:]}"
                )
            if date_index + 1 < len(parts):
                metadata["broker"] = parts[date_index + 1]
            if date_index + 2 < len(parts):
                metadata["subject"] = "_".join(parts[date_index + 2 :])
            return metadata

        if len(parts) >= 3:
            metadata["ticker"] = parts[0]
            metadata["publish_date"] = parts[1]
            if re.fullmatch(r"\d{8}", metadata["publish_date"]):
                metadata["publish_date_iso"] = (
                    f"{metadata['publish_date'][:4]}-{metadata['publish_date'][4:6]}-{metadata['publish_date'][6:]}"
                )
            metadata["broker"] = parts[2]
            if len(parts) > 3:
                metadata["subject"] = "_".join(parts[3:])
        return metadata

    def _parse_filing_filename(self, stem: str) -> dict[str, Any]:
        parts = [part for part in re.split(r"[_\s]+", stem) if part]
        metadata: dict[str, Any] = {
            "ticker": "UNKNOWN",
            "issuer": "UNKNOWN",
            "period_end": "UNKNOWN",
            "report_type": "filing",
            "source_title": stem,
        }

        if parts:
            metadata["ticker"] = parts[0].strip().upper() if parts[0].isalpha() else parts[0].strip()

        date_index = -1
        for index, part in enumerate(parts):
            normalized_date = self._compact_date(part)
            if normalized_date:
                date_index = index
                metadata["period_end"] = normalized_date
                metadata["period_end_iso"] = self._iso_date(normalized_date)
                break

        title_parts = parts[1:]
        if date_index >= 0:
            title_parts = parts[date_index + 1 :]

        report_type = self._normalize_report_type(" ".join(title_parts)) or self._infer_report_type_from_period(
            metadata.get("period_end")
        )
        if report_type:
            metadata["report_type"] = report_type

        if title_parts:
            metadata["source_title"] = "_".join(title_parts)
            issuer_candidate_parts = [
                cleaned_part
                for part in title_parts
                if (cleaned_part := self._clean_issuer_candidate(part))
            ]
            if issuer_candidate_parts:
                metadata["issuer"] = issuer_candidate_parts[-1]

        query_period = self._extract_query_period_end(stem)
        if metadata["period_end"] == "UNKNOWN" and query_period:
            metadata["period_end"] = query_period
            metadata["period_end_iso"] = self._iso_date(query_period)

        return metadata

    def _clean_issuer_candidate(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text or self._compact_date(text):
            return ""

        lower_text = text.lower()
        if lower_text in {
            "annual",
            "semiannual",
            "semi_annual",
            "quarterly",
            "quarter",
            "report",
            "filing",
            "10-k",
            "10k",
            "10-q",
            "10q",
            "20-f",
            "20f",
            "q1",
            "q2",
            "q3",
            "q4",
        }:
            return ""

        cleaned = re.sub(r"\d{4}\s*年?", "", text)
        cleaned = re.sub(r"(年度报告|年报|半年度报告|半年报|中报|季度报告|一季报|二季报|三季报|四季报|季报)", "", cleaned)
        cleaned = re.sub(r"(annual|semiannual|quarterly|interim|report|filing)", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip("_-— 　")
        return cleaned

    def _compact_date(self, value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if iso_match:
            return "".join(iso_match.groups())
        compact_match = re.fullmatch(r"\d{8}", text)
        if compact_match:
            return text
        return None

    def _iso_date(self, value: str | None) -> str | None:
        compact = self._compact_date(value)
        if not compact:
            return None
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"

    def _normalize_report_type(self, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        normalized_text = re.sub(r"[\s_]+", "_", text)
        for report_type, aliases in FILING_REPORT_TYPE_ALIASES.items():
            if normalized_text == report_type:
                return report_type
            for alias in aliases:
                alias_text = alias.lower().replace(" ", "_")
                if normalized_text == alias_text or alias_text in normalized_text or alias.lower() in text:
                    return report_type
        q_match = re.search(r"\bq[1-4]\b", normalized_text)
        if q_match:
            return "quarterly_report"
        return None

    def _infer_report_type_from_period(self, period_end: Any) -> str | None:
        compact = self._compact_date(period_end)
        if not compact:
            return None
        month_day = compact[4:]
        if month_day == "1231":
            return "annual_report"
        if month_day == "0630":
            return "semiannual_report"
        if month_day in {"0331", "0930"}:
            return "quarterly_report"
        return None

    def _normalize_statement_type(self, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        normalized_text = re.sub(r"[\s_]+", "_", text)
        for statement_type, keywords in FILING_STATEMENT_KEYWORDS.items():
            if normalized_text == statement_type:
                return statement_type
            for keyword in keywords:
                keyword_text = keyword.lower().replace(" ", "_")
                if normalized_text == keyword_text or keyword.lower() in text:
                    return statement_type
        return None

    def _infer_statement_type(self, text: str) -> str | None:
        lowered = self._normalize_text(text).lower()
        if not lowered:
            return None
        for statement_type, keywords in FILING_STATEMENT_KEYWORDS.items():
            if any(keyword.lower() in lowered for keyword in keywords):
                return statement_type
        return None

    def _render_glossary_entry(self, term: str, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        aliases = self._extract_aliases(row)
        related_terms = self._extract_listish(row.get("related_terms") or row.get("related") or row.get("see_also"))
        category = self._clean_scalar(row.get("category") or row.get("group") or row.get("topic"))
        definition = self._clean_scalar(
            row.get("definition")
            or row.get("meaning")
            or row.get("description")
            or row.get("content")
            or row.get("text")
        )
        example = self._clean_scalar(row.get("example") or row.get("examples"))
        notes = self._clean_scalar(row.get("notes"))

        content_lines = [f"术语: {term}"]
        if aliases:
            content_lines.append(f"别名: {', '.join(aliases)}")
        if category:
            content_lines.append(f"分类: {category}")
        if definition:
            content_lines.append(f"定义: {definition}")
        if related_terms:
            content_lines.append(f"相关术语: {', '.join(related_terms)}")
        if example:
            content_lines.append(f"示例: {example}")
        if notes:
            content_lines.append(f"备注: {notes}")

        payload = {
            "term": term,
            "aliases": aliases,
            "related_terms": related_terms,
            "category": category,
            "definition": definition,
            "example": example,
            "notes": notes,
        }
        return "\n".join(content_lines).strip(), payload

    def _extract_glossary_term(self, row: dict[str, Any]) -> str | None:
        for key in ("term", "name", "title", "concept", "keyword"):
            value = self._clean_scalar(row.get(key))
            if value:
                return value
        return None

    def _extract_aliases(self, row: dict[str, Any]) -> list[str]:
        aliases = row.get("aliases") or row.get("alias") or row.get("synonyms")
        return self._extract_listish(aliases)

    def _extract_listish(self, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [self._clean_scalar(item) for item in value if self._clean_scalar(item)]
        if isinstance(value, dict):
            return [self._clean_scalar(item) for item in value.values() if self._clean_scalar(item)]
        if isinstance(value, str):
            parts = re.split(r"[，,;/|、]\s*", value.strip())
            return [part.strip() for part in parts if part.strip()]
        return [self._clean_scalar(value)] if self._clean_scalar(value) else []

    def _clean_scalar(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return str(value).strip()

    def _read_text_file(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")

    def _read_markup_file(self, path: Path) -> str:
        raw = self._read_text_file(path)
        raw = re.sub(r"(?is)<(script|style).*?</\1>", "\n", raw)
        raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
        raw = re.sub(r"(?i)</(p|div|li|tr|table|section|article|h[1-6])>", "\n", raw)
        raw = re.sub(r"(?is)<[^>]+>", " ", raw)
        return self._normalize_text(html.unescape(raw))

    def _read_filing_csv_text(self, path: Path) -> str:
        rows = self._read_csv_rows(path)
        lines = [path.stem]
        for row_index, row in enumerate(rows, start=1):
            cells = [
                f"{key}: {self._clean_scalar(value)}"
                for key, value in row.items()
                if self._clean_scalar(value)
            ]
            if cells:
                lines.append(f"行 {row_index}: " + "；".join(cells))
        return "\n".join(lines)

    def _read_filing_json_text(self, path: Path) -> str:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        lines = [path.stem]
        self._append_json_lines(data, lines=lines, prefix="")
        return "\n".join(lines)

    def _append_json_lines(self, value: Any, lines: list[str], prefix: str, max_depth: int = 6) -> None:
        if max_depth <= 0:
            lines.append(f"{prefix}: {self._clean_scalar(value)}" if prefix else self._clean_scalar(value))
            return
        if isinstance(value, dict):
            scalar_items: list[str] = []
            nested_items: list[tuple[str, Any]] = []
            for key, item in value.items():
                key_text = self._clean_scalar(key)
                if isinstance(item, (dict, list)):
                    nested_items.append((key_text, item))
                else:
                    cleaned = self._clean_scalar(item)
                    if cleaned:
                        scalar_items.append(f"{key_text}: {cleaned}")
            if scalar_items:
                label = prefix or "记录"
                lines.append(f"{label}: " + "；".join(scalar_items))
            for key, item in nested_items:
                child_prefix = f"{prefix} > {key}" if prefix else key
                self._append_json_lines(item, lines=lines, prefix=child_prefix, max_depth=max_depth - 1)
            return
        if isinstance(value, list):
            for index, item in enumerate(value, start=1):
                child_prefix = f"{prefix}[{index}]" if prefix else f"记录[{index}]"
                self._append_json_lines(item, lines=lines, prefix=child_prefix, max_depth=max_depth - 1)
            return
        cleaned = self._clean_scalar(value)
        if cleaned:
            lines.append(f"{prefix}: {cleaned}" if prefix else cleaned)

    def _read_csv_rows(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]

    def _read_json_rows(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return list(self._iter_structured_rows(data))

    def _read_yaml_rows(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return list(self._iter_structured_rows(data))

    def _iter_structured_rows(self, data: Any) -> Iterable[dict[str, Any]]:
        if data is None:
            return []
        if isinstance(data, list):
            rows: list[dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    rows.append(dict(item))
                else:
                    rows.append({"term": str(item), "definition": ""})
            return rows
        if isinstance(data, dict):
            rows = []
            for key, value in data.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault("term", key)
                    rows.append(row)
                else:
                    rows.append({"term": key, "definition": value})
            return rows
        return []

    def _parse_glossary_markdown_entries(self, text: str, fallback_term: str) -> list[tuple[str, dict[str, Any]]]:
        lines = self._normalize_text(text).splitlines()
        entries: list[tuple[str, dict[str, Any]]] = []
        current_term = fallback_term
        current_term_from_heading = False
        current_lines: list[str] = []

        def flush(term: str | None, body_lines: list[str], force: bool = False) -> None:
            body = "\n".join(body_lines).strip()
            if not body and not force:
                return
            if term is None:
                return
            entry: dict[str, Any] = {"term": term, "definition": body}
            entries.append((term, entry))

        for line in lines:
            heading = HEADING_PATTERN.match(line.strip())
            bullet = GLOSSARY_TERM_PATTERN.match(line.strip())
            if heading:
                flush(current_term, current_lines, force=current_term_from_heading)
                current_term = heading.group(2).strip()
                current_term_from_heading = True
                current_lines = []
                continue
            if bullet:
                flush(current_term, current_lines, force=current_term_from_heading)
                current_term = bullet.group(1).strip()
                current_term_from_heading = True
                current_lines = [bullet.group(2).strip()]
                continue
            current_lines.append(line)

        flush(current_term, current_lines, force=current_term_from_heading)

        if not entries and lines:
            body = "\n".join(lines).strip()
            if body:
                entries.append((fallback_term, {"term": fallback_term, "definition": body}))

        return entries

    def _chunk_glossary_entries(
        self,
        entries: list[tuple[str, dict[str, Any]]],
        metadata: dict[str, Any],
        source_path: Path,
    ) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for entry_index, (term, row) in enumerate(entries):
            entry_text, entry_payload = self._render_glossary_entry(term, row)
            token_chunks = self._split_text_chunks(
                entry_text,
                max_tokens=self.settings.knowledge_base.glossary_chunk_tokens,
                overlap=self.settings.knowledge_base.glossary_chunk_overlap,
            )
            if not token_chunks:
                continue

            for chunk_index, text_chunk in enumerate(token_chunks):
                payload = dict(metadata)
                payload.update(
                    {
                        "term": term,
                        "doc_type": "glossary",
                        "section_path": [term],
                        "section_path_text": term,
                        "section_depth": 1,
                        "entry_index": entry_index,
                        "chunk_index": chunk_index,
                        "chunk_total": len(token_chunks),
                        "chunk_strategy": "glossary_term_token_window",
                        "chunk_role": "evidence",
                    }
                )
                payload.update(entry_payload)
                self._apply_text_chunk_metadata(payload, text_chunk)
                rendered_content = self._compose_chunk_text(
                    metadata=payload,
                    chunk_text=text_chunk.text,
                    title=term,
                )
                payload["content"] = rendered_content
                chunks.append(
                    KnowledgeChunk(
                        id=self._make_chunk_id(source_path, entry_index, chunk_index),
                        content=rendered_content,
                        payload=payload,
                    )
                )
        return chunks

    def _build_report_summary_chunk(
        self,
        path: Path,
        metadata: dict[str, Any],
        summary_bits: list[str],
    ) -> KnowledgeChunk | None:
        if not summary_bits:
            return None

        title = metadata.get("source_title") or path.stem
        preview = "\n".join(f"- {item}" for item in summary_bits if item).strip()
        if not preview:
            return None

        model_summary = self._generate_model_summary(metadata=metadata, text=preview)
        summary_metadata = dict(metadata)
        summary_strategy = "document_summary_abstractive_ollama" if model_summary else "document_summary_extractive"
        summary_metadata.update(
            {
                "section_path": ["summary"],
                "section_path_text": "summary",
                "section_title": "summary",
                "section_depth": 1,
                "section_index": "summary",
                "chunk_index": 0,
                "chunk_total": 1,
                "chunk_strategy": summary_strategy,
                "chunk_role": "summary",
                "summary_scope": "document",
            }
        )
        if model_summary:
            summary_metadata["summary_json"] = model_summary

        summary_text = (
            json.dumps(model_summary, ensure_ascii=False, indent=2)
            if model_summary
            else preview[:REPORT_SUMMARY_MAX_CHARS]
        )

        rendered_content = self._compose_chunk_text(
            metadata=summary_metadata,
            chunk_text=summary_text,
            title=f"{title} 摘要",
        )
        return KnowledgeChunk(
            id=self._make_chunk_id(path, "summary", 0),
            content=rendered_content,
            payload={**summary_metadata, "content": rendered_content},
        )

    def _generate_model_summary(self, metadata: dict[str, Any], text: str) -> dict[str, Any] | None:
        """Generate a compact abstractive document summary with local Ollama.

        The KB build should remain usable when the local model is unavailable, so
        all failures fall back to the extractive summary path.
        """

        clean_text = self._truncate_text(text, REPORT_SUMMARY_MODEL_INPUT_MAX_CHARS)
        if not clean_text:
            return None

        system_prompt = """你是金融知识库的结构化提炼引擎。你的任务是基于输入的研报/财报文本，生成用于混合检索（Hybrid RAG）的高质量 JSON 元数据。

严格约束：
1. 仅使用原文信息，严禁编造数据、机构或评级。缺失信息必须填 null。
2. 提取必须包含具体的数值、单位和同比变化。
3. 必须输出纯 JSON 对象，严禁任何解释性文本、严禁输出 Markdown 代码块符号。

期望的 JSON 结构：
{
  "document_type": "research_report | financial_filing | announcement | unknown",
  "title": "文档标题或核心主题",
  "core_summary": [
    "3-5条核心要点（每条需包含关键事实、数据或业务动作）"
  ],
  "financial_metrics": [
    {
      "metric": "指标名称（如营收、净利润）",
      "value": "数值和单位（如100亿元）"
    }
  ],
  "investment_view": {
    "rating": "评级（未提及填 null）",
    "target_price": "目标价（未提及填 null）"
  },
  "catalysts_and_risks": [
    "明确提到的催化剂或风险因素（提炼为短语）"
  ],
  "retrieval_keywords": [
    "适合检索的股票代码、行业简称、专有名词、产品名（限10个以内）"
  ]
}"""
        user_prompt = f"""输入元数据：
- doc_type: {metadata.get("doc_type") or "unknown"}
- ticker: {metadata.get("ticker") or None}
- publish_date: {metadata.get("publish_date") or metadata.get("publish_date_iso") or None}

输入文本：
{clean_text}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            from utils.config import load_config

            config = load_config()
            provider = str(config.get("llm_provider", "ollama")).strip().lower()
            if provider == "gemini":
                from llm.gemini_client import gemini_chat

                raw_response = gemini_chat(
                    messages,
                    timeout=REPORT_SUMMARY_MODEL_TIMEOUT_SECONDS,
                    options={"temperature": 0.1},
                )
            elif provider == "openrouter":
                from llm.openrouter_client import openrouter_chat

                raw_response = openrouter_chat(
                    messages,
                    timeout=REPORT_SUMMARY_MODEL_TIMEOUT_SECONDS,
                    options={"temperature": 0.1},
                )
            else:
                from llm.ollama_client import ollama_chat

                raw_response = ollama_chat(
                    messages,
                    timeout=REPORT_SUMMARY_MODEL_TIMEOUT_SECONDS,
                    model_name=self.settings.llm.ollama_model,
                    base_url=self.settings.llm.ollama_base_url,
                    options={"temperature": 0.1},
                )
        except Exception:
            return None

        parsed = self._parse_model_summary_json(raw_response)
        if not parsed:
            return None
        return self._normalize_model_summary(parsed)

    def _parse_model_summary_json(self, raw_response: Any) -> dict[str, Any] | None:
        text = str(raw_response or "").strip()
        if not text:
            return None

        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        return parsed if isinstance(parsed, dict) else None

    def _normalize_model_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        def clean_optional(value: Any) -> str | None:
            if value is None:
                return None
            text = str(value).strip()
            if not text or text.lower() in {"null", "none", "n/a", "未提及"}:
                return None
            return text

        def clean_list(value: Any, limit: int) -> list[str]:
            if value is None:
                return []
            items = value if isinstance(value, list) else [value]
            cleaned: list[str] = []
            for item in items:
                text = clean_optional(item)
                if not text or text in cleaned:
                    continue
                cleaned.append(text)
                if len(cleaned) >= limit:
                    break
            return cleaned

        metrics: list[dict[str, str | None]] = []
        raw_metrics = summary.get("financial_metrics")
        if isinstance(raw_metrics, list):
            for item in raw_metrics:
                if not isinstance(item, dict):
                    continue
                metric = clean_optional(item.get("metric"))
                value = clean_optional(item.get("value"))
                if metric or value:
                    metrics.append({"metric": metric, "value": value})

        investment_view = summary.get("investment_view")
        if not isinstance(investment_view, dict):
            investment_view = {}

        document_type = clean_optional(summary.get("document_type")) or "unknown"
        if document_type not in {"research_report", "financial_filing", "announcement", "unknown"}:
            document_type = "unknown"

        return {
            "document_type": document_type,
            "title": clean_optional(summary.get("title")),
            "core_summary": clean_list(summary.get("core_summary"), limit=5),
            "financial_metrics": metrics[:12],
            "investment_view": {
                "rating": clean_optional(investment_view.get("rating")),
                "target_price": clean_optional(investment_view.get("target_price")),
            },
            "catalysts_and_risks": clean_list(summary.get("catalysts_and_risks"), limit=12),
            "retrieval_keywords": clean_list(summary.get("retrieval_keywords"), limit=10),
        }

    def _section_summary_source(self, section_path_text: str, text: str) -> str:
        body = self._truncate_text(text, max_chars=900)
        if not body:
            return ""
        return f"{section_path_text}: {body}"

    def _section_preview(self, section_path_text: str, text: str) -> str:
        lead = self._lead_sentences(text, max_sentences=2, max_chars=260)
        if not lead:
            return ""
        return f"{section_path_text}: {lead}"

    def _lead_sentences(self, text: str, max_sentences: int = 2, max_chars: int = 260) -> str:
        normalized = self._normalize_text(text)
        if not normalized:
            return ""

        sentences = re.split(r"(?<=[。！？!?；;])\s*", normalized)
        selected: list[str] = []
        total_len = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            selected.append(sentence)
            total_len += len(sentence)
            if len(selected) >= max_sentences or total_len >= max_chars:
                break

        if not selected:
            return self._truncate_text(normalized, max_chars)
        return self._truncate_text("".join(selected), max_chars)

    def _truncate_text(self, text: str, max_chars: int) -> str:
        cleaned = self._normalize_text(text)
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[: max_chars - 1].rstrip() + "…"

    def _read_pdf_text(self, path: Path) -> list[str]:
        reader = PdfReader(str(path))
        return [page.extract_text() or "" for page in reader.pages]

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    def _make_chunk_id(self, path: Path, section_index: int | str, chunk_index: int) -> str:
        relative = self._relative_path(path).replace("\\", "/")
        return f"{relative}:{section_index}:{chunk_index}"

    def _normalize_text(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()

    def _parse_query_context(self, query: str) -> KnowledgeQueryContext:
        normalized_query = self._normalize_text(query)
        ticker = self._extract_query_ticker(normalized_query)
        publish_date = self._extract_query_date(normalized_query)
        period_end = self._extract_query_period_end(normalized_query)
        report_type = self._extract_query_report_type(normalized_query)
        statement_type = self._extract_query_statement_type(normalized_query)
        search_base = normalized_query
        if publish_date:
            for candidate in self._normalize_date_candidates(publish_date):
                search_base = search_base.replace(candidate, " ")
        if period_end:
            for candidate in self._normalize_date_candidates(period_end):
                search_base = search_base.replace(candidate, " ")
        search_terms = self._extract_search_terms(search_base, max_terms=32)
        if ticker:
            search_terms.extend(self._extract_search_terms(ticker, max_terms=4))
        if publish_date:
            search_terms.extend(self._normalize_date_candidates(publish_date))
        if period_end:
            search_terms.extend(self._normalize_date_candidates(period_end))
        if report_type:
            search_terms.extend(self._extract_search_terms(report_type, max_terms=4))
        if statement_type:
            search_terms.extend(self._extract_search_terms(statement_type, max_terms=4))
        search_terms = self._deduplicate_terms(search_terms)
        return KnowledgeQueryContext(
            raw_query=query,
            normalized_query=normalized_query,
            search_terms=search_terms,
            ticker=ticker,
            publish_date=publish_date,
            period_end=period_end,
            report_type=report_type,
            statement_type=statement_type,
        )

    def _extract_query_ticker(self, query: str) -> str | None:
        labeled_match = re.search(
            r"(?:ticker|代码|股票代码|标的)[:：]?\s*([A-Za-z0-9]{1,10})",
            query,
            flags=re.IGNORECASE,
        )
        if labeled_match:
            candidate = labeled_match.group(1).strip()
            if candidate.isalpha():
                return candidate.upper()
            return candidate

        for token in re.findall(r"\b[A-Z]{1,5}\b|\b\d{6}\b|\b0\d{3,4}\b", query):
            token = token.strip()
            if token.isdigit() and len(token) == 6:
                return token
            if token.isdigit() and token.startswith("0") and len(token) in {4, 5}:
                return token
            if token.isalpha() and token.upper() == token:
                return token.upper()
        return None

    def _extract_query_date(self, query: str) -> str | None:
        iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", query)
        if iso_match:
            return iso_match.group(0)
        compact_match = re.search(r"\b\d{8}\b", query)
        if compact_match:
            return compact_match.group(0)
        return None

    def _extract_query_period_end(self, query: str) -> str | None:
        year = r"(20\d{2}|19\d{2})"
        q_map = {
            "1": "0331",
            "一": "0331",
            "2": "0630",
            "二": "0630",
            "3": "0930",
            "三": "0930",
            "4": "1231",
            "四": "1231",
        }

        q_match = re.search(rf"{year}\s*[qQ]\s*([1-4])", query)
        if q_match:
            return f"{q_match.group(1)}{q_map[q_match.group(2)]}"

        cn_q_match = re.search(rf"{year}\s*年?\s*(?:第?\s*)?([一二三四1-4])\s*(?:季度|季报)", query)
        if cn_q_match:
            return f"{cn_q_match.group(1)}{q_map[cn_q_match.group(2)]}"

        annual_match = re.search(rf"{year}\s*年?\s*(?:年报|年度报告|annual report|10-k|10k|20-f|20f)", query, flags=re.IGNORECASE)
        if annual_match:
            return f"{annual_match.group(1)}1231"

        semiannual_match = re.search(rf"{year}\s*年?\s*(?:中报|半年报|半年度报告|semiannual|interim|h1|1h)", query, flags=re.IGNORECASE)
        if semiannual_match:
            return f"{semiannual_match.group(1)}0630"

        return None

    def _extract_query_report_type(self, query: str) -> str | None:
        return self._normalize_report_type(query)

    def _extract_query_statement_type(self, query: str) -> str | None:
        return self._normalize_statement_type(query)

    def _normalize_date_candidates(self, value: str | None) -> list[str]:
        if not value:
            return []

        normalized = value.strip()
        if not normalized:
            return []

        candidates: list[str] = [normalized]
        compact = normalized.replace("-", "")
        if compact not in candidates:
            candidates.append(compact)
        if re.fullmatch(r"\d{8}", compact):
            iso_value = f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
            if iso_value not in candidates:
                candidates.append(iso_value)
        return self._deduplicate_terms(candidates)

    def _extract_search_terms(self, text: str, max_terms: int = 40) -> list[str]:
        normalized = self._normalize_text(text).lower()
        if not normalized:
            return []

        tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", normalized, flags=re.IGNORECASE)
        terms: list[str] = []
        seen: set[str] = set()

        for token in tokens:
            token = token.strip().lower()
            if not token:
                continue

            candidate_terms: list[str] = []
            if re.fullmatch(r"[a-z0-9]+", token):
                if len(token) >= 2:
                    candidate_terms.append(token)
            else:
                if len(token) >= 2:
                    candidate_terms.append(token)
                    if len(token) >= 3:
                        candidate_terms.extend(self._expand_chinese_term(token))

            for candidate in candidate_terms:
                normalized_candidate = candidate.strip().lower()
                if len(normalized_candidate) < 2 or normalized_candidate in seen:
                    continue
                seen.add(normalized_candidate)
                terms.append(normalized_candidate)
                if len(terms) >= max_terms:
                    return terms

        return terms

    def _expand_chinese_term(self, token: str) -> list[str]:
        spans: list[str] = []
        if len(token) < 3:
            return spans

        for window in (2, 3):
            if len(token) < window:
                continue
            for index in range(len(token) - window + 1):
                spans.append(token[index : index + window])
        return spans

    def _deduplicate_terms(self, terms: Sequence[str]) -> list[str]:
        deduplicated: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = str(term).strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(normalized)
        return deduplicated

    def _payload_matches_date(self, payload: dict[str, Any], publish_date: str) -> bool:
        candidates = self._normalize_date_candidates(publish_date)
        if not candidates:
            return False

        payload_values = {
            str(payload.get("publish_date") or "").strip(),
            str(payload.get("publish_date_iso") or "").strip(),
        }
        return any(candidate in payload_values for candidate in candidates)

    def _payload_matches_period_end(self, payload: dict[str, Any], period_end: str) -> bool:
        candidates = self._normalize_date_candidates(period_end)
        if not candidates:
            return False

        payload_values = {
            str(payload.get("period_end") or "").strip(),
            str(payload.get("period_end_iso") or "").strip(),
        }
        return any(candidate in payload_values for candidate in candidates)

    def _load_document_chunks(self, source_hash: str) -> list[KnowledgeSearchHit]:
        collection_name = self.settings.knowledge_base.collection_name
        if not source_hash or not self.qdrant_client.collection_exists(collection_name=collection_name):
            return []

        scroll_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="source_hash",
                    match=qdrant_models.MatchValue(value=source_hash),
                )
            ]
        )

        hits: list[KnowledgeSearchHit] = []
        offset = None
        while True:
            records, offset = self.qdrant_client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                payload = dict(record.payload or {})
                hits.append(
                    KnowledgeSearchHit(
                        id=str(record.id),
                        score=0.0,
                        content=str(payload.get("content", "")),
                        payload=payload,
                    )
                )
            if offset is None:
                break

        hits.sort(key=lambda item: self._chunk_sort_key(item.payload))
        return hits

    def _expand_hit_with_neighbors(
        self,
        hit: KnowledgeSearchHit,
        document_chunks: list[KnowledgeSearchHit],
        neighbor_window: int = 1,
    ) -> KnowledgeSearchHit:
        if not document_chunks:
            return hit

        payload = dict(hit.payload)
        chunk_role = str(payload.get("chunk_role") or "").lower()
        evidence_chunks = [chunk for chunk in document_chunks if str(chunk.payload.get("chunk_role") or "").lower() == "evidence"]
        if not evidence_chunks:
            return hit

        if chunk_role == "summary":
            return self._expand_summary_hit(hit, evidence_chunks, neighbor_window=neighbor_window)

        paragraph_chunks = self._same_paragraph_chunks(hit, evidence_chunks)
        if not paragraph_chunks:
            return self._expand_hit_with_fixed_neighbors(hit, evidence_chunks, neighbor_window=neighbor_window)

        target_index = self._find_hit_index(hit, paragraph_chunks)
        if target_index is None:
            return self._expand_hit_with_fixed_neighbors(hit, evidence_chunks, neighbor_window=neighbor_window)

        paragraph_token_count = self._paragraph_context_token_count(paragraph_chunks)
        if paragraph_token_count <= CONTEXT_EXPANSION_TOKEN_LIMIT:
            selected_chunks = paragraph_chunks
            expansion_mode = "full_paragraph"
        else:
            selected_indices = self._select_bounded_paragraph_indices(
                hit=hit,
                paragraph_chunks=paragraph_chunks,
                target_index=target_index,
                token_limit=CONTEXT_EXPANSION_TOKEN_LIMIT,
            )
            selected_chunks = [paragraph_chunks[index] for index in selected_indices]
            expansion_mode = "bounded_paragraph_window"

        return self._render_paragraph_expanded_hit(
            hit=hit,
            selected_chunks=selected_chunks,
            expansion_mode=expansion_mode,
            token_limit=CONTEXT_EXPANSION_TOKEN_LIMIT,
        )

    def _expand_summary_hit(
        self,
        hit: KnowledgeSearchHit,
        evidence_chunks: list[KnowledgeSearchHit],
        neighbor_window: int,
    ) -> KnowledgeSearchHit:
        context_chunks = evidence_chunks[: max(2, neighbor_window * 2)]
        return self._render_fixed_neighbor_expansion(
            hit=hit,
            neighbor_chunks=context_chunks,
            neighbor_window=neighbor_window,
            expansion_mode="summary_seed_evidence",
        )

    def _expand_hit_with_fixed_neighbors(
        self,
        hit: KnowledgeSearchHit,
        evidence_chunks: list[KnowledgeSearchHit],
        neighbor_window: int,
    ) -> KnowledgeSearchHit:
        payload = dict(hit.payload)
        section_key = str(payload.get("section_path_text") or "")
        same_section = [
            chunk
            for chunk in evidence_chunks
            if str(chunk.payload.get("section_path_text") or "") == section_key
        ]
        context_chunks = sorted(same_section or evidence_chunks, key=lambda item: self._chunk_sort_key(item.payload))
        target_index = self._find_hit_index(hit, context_chunks)
        if target_index is None:
            return hit

        start = max(0, target_index - neighbor_window)
        end = min(len(context_chunks), target_index + neighbor_window + 1)
        return self._render_fixed_neighbor_expansion(
            hit=hit,
            neighbor_chunks=context_chunks[start:end],
            neighbor_window=neighbor_window,
            expansion_mode="fixed_neighbor_window",
        )

    def _render_fixed_neighbor_expansion(
        self,
        hit: KnowledgeSearchHit,
        neighbor_chunks: list[KnowledgeSearchHit],
        neighbor_window: int,
        expansion_mode: str,
    ) -> KnowledgeSearchHit:
        rendered_neighbors: list[str] = []
        neighbor_ids: list[str] = []
        for neighbor in neighbor_chunks:
            if neighbor.id == hit.id:
                continue
            neighbor_ids.append(neighbor.id)
            neighbor_title = str(neighbor.payload.get("section_path_text") or neighbor.payload.get("source_title") or neighbor.id)
            rendered_neighbors.append(f"【邻近块: {neighbor_title}】\n{neighbor.content}")

        if not rendered_neighbors:
            return hit

        expanded_content = hit.content.rstrip() + "\n\n【相邻证据】\n\n" + "\n\n".join(rendered_neighbors)
        expanded_payload = dict(hit.payload)
        expanded_payload["neighbor_ids"] = neighbor_ids
        expanded_payload["expanded_from"] = hit.id
        expanded_payload["expanded_neighbor_window"] = neighbor_window
        expanded_payload["expanded_context_mode"] = expansion_mode
        expanded_payload["expanded_context_token_count"] = self._token_count(expanded_content)
        return KnowledgeSearchHit(
            id=hit.id,
            score=hit.score,
            content=expanded_content,
            payload=expanded_payload,
        )

    def _same_paragraph_chunks(
        self,
        hit: KnowledgeSearchHit,
        evidence_chunks: list[KnowledgeSearchHit],
    ) -> list[KnowledgeSearchHit]:
        paragraph_index = self._optional_int(hit.payload.get("paragraph_index"))
        if paragraph_index is None:
            return []

        return sorted(
            [
                chunk
                for chunk in evidence_chunks
                if self._payload_matches_paragraph(hit.payload, chunk.payload)
            ],
            key=lambda item: self._chunk_sort_key(item.payload),
        )

    def _payload_matches_paragraph(self, target: dict[str, Any], candidate: dict[str, Any]) -> bool:
        paragraph_index = self._optional_int(target.get("paragraph_index"))
        if paragraph_index is None:
            return False
        if self._optional_int(candidate.get("paragraph_index")) != paragraph_index:
            return False

        for key in ("page_start", "page_end", "section_index", "section_path_text"):
            if self._payload_key_text(candidate, key) != self._payload_key_text(target, key):
                return False
        return True

    def _find_hit_index(self, hit: KnowledgeSearchHit, context_chunks: list[KnowledgeSearchHit]) -> int | None:
        target_index = next((index for index, candidate in enumerate(context_chunks) if candidate.id == hit.id), None)
        if target_index is not None:
            return target_index
        return next(
            (
                index
                for index, candidate in enumerate(context_chunks)
                if self._chunk_sort_key(candidate.payload) == self._chunk_sort_key(hit.payload)
            ),
            None,
        )

    def _paragraph_context_token_count(self, paragraph_chunks: list[KnowledgeSearchHit]) -> int:
        token_counts = [
            value
            for value in (self._optional_int(chunk.payload.get("paragraph_token_count")) for chunk in paragraph_chunks)
            if value is not None
        ]
        if token_counts:
            return max(token_counts)
        return self._token_count(self._join_chunk_parts(self._chunk_body_text(chunk) for chunk in paragraph_chunks))

    def _select_bounded_paragraph_indices(
        self,
        hit: KnowledgeSearchHit,
        paragraph_chunks: list[KnowledgeSearchHit],
        target_index: int,
        token_limit: int,
    ) -> list[int]:
        selected_indices: set[int] = {target_index}
        left_index = target_index - 1
        right_index = target_index + 1
        left_blocked = left_index < 0
        right_blocked = right_index >= len(paragraph_chunks)
        prefer_left = True

        while not (left_blocked and right_blocked):
            sides = ("left", "right") if prefer_left else ("right", "left")
            added = False

            for side in sides:
                if side == "left":
                    if left_blocked:
                        continue
                    candidate_index = left_index
                else:
                    if right_blocked:
                        continue
                    candidate_index = right_index

                if candidate_index < 0 or candidate_index >= len(paragraph_chunks):
                    if side == "left":
                        left_blocked = True
                    else:
                        right_blocked = True
                    continue

                candidate_indices = selected_indices | {candidate_index}
                candidate_chunks = [paragraph_chunks[index] for index in sorted(candidate_indices)]
                if self._selected_chunk_token_count(candidate_chunks) <= token_limit:
                    selected_indices.add(candidate_index)
                    if side == "left":
                        left_index -= 1
                        left_blocked = left_index < 0
                    else:
                        right_index += 1
                        right_blocked = right_index >= len(paragraph_chunks)
                    prefer_left = not prefer_left
                    added = True
                    break

                if side == "left":
                    left_blocked = True
                else:
                    right_blocked = True

            if not added:
                break

        return [index for index in sorted(selected_indices) if 0 <= index < len(paragraph_chunks)]

    def _render_paragraph_expanded_hit(
        self,
        hit: KnowledgeSearchHit,
        selected_chunks: list[KnowledgeSearchHit],
        expansion_mode: str,
        token_limit: int,
    ) -> KnowledgeSearchHit:
        if len(selected_chunks) <= 1:
            return hit

        expanded_content = self._render_paragraph_context_content(hit, selected_chunks)
        expanded_payload = dict(hit.payload)
        selected_ids = [chunk.id for chunk in selected_chunks]
        expanded_payload["context_chunk_ids"] = selected_ids
        expanded_payload["neighbor_ids"] = [chunk_id for chunk_id in selected_ids if chunk_id != hit.id]
        expanded_payload["expanded_from"] = hit.id
        expanded_payload["expanded_context_mode"] = expansion_mode
        expanded_payload["expanded_context_token_limit"] = token_limit
        expanded_payload["expanded_context_body_token_count"] = self._selected_chunk_token_count(selected_chunks)
        expanded_payload["expanded_context_token_count"] = self._token_count(expanded_content)
        return KnowledgeSearchHit(
            id=hit.id,
            score=hit.score,
            content=expanded_content,
            payload=expanded_payload,
        )

    def _selected_chunk_token_count(self, selected_chunks: list[KnowledgeSearchHit]) -> int:
        return sum(self._chunk_token_count(chunk) for chunk in selected_chunks)

    def _chunk_token_count(self, chunk: KnowledgeSearchHit) -> int:
        token_count = self._optional_int(chunk.payload.get("token_count"))
        if token_count is not None:
            return token_count
        return self._token_count(self._chunk_body_text(chunk))

    def _render_paragraph_context_content(
        self,
        hit: KnowledgeSearchHit,
        selected_chunks: list[KnowledgeSearchHit],
    ) -> str:
        header = self._content_header(hit.content)
        rendered_chunks: list[str] = []
        for chunk in selected_chunks:
            body = self._chunk_body_text(chunk)
            if not body:
                continue
            position = self._optional_int(chunk.payload.get("paragraph_chunk_index"))
            total = self._optional_int(chunk.payload.get("paragraph_chunk_total"))
            if position is None:
                position = len(rendered_chunks)
            if total is None:
                total = len(selected_chunks)
            role = "命中块" if chunk.id == hit.id else "同段落块"
            rendered_chunks.append(f"【{role} {position + 1}/{total}】\n{body}")

        if not rendered_chunks:
            return hit.content
        if not header:
            return "【同段落上下文】\n\n" + "\n\n".join(rendered_chunks)
        return header.rstrip() + "\n\n【同段落上下文】\n\n" + "\n\n".join(rendered_chunks)

    def _chunk_body_text(self, chunk: KnowledgeSearchHit) -> str:
        chunk_text = str(chunk.payload.get("chunk_text") or "").strip()
        if chunk_text:
            return chunk_text
        return self._content_body(chunk.content)

    def _content_header(self, content: str) -> str:
        return str(content or "").split("\n\n", 1)[0].strip()

    def _content_body(self, content: str) -> str:
        parts = str(content or "").split("\n\n", 1)
        return parts[1].strip() if len(parts) > 1 else str(content or "").strip()

    def _optional_int(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _payload_key_text(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        return "" if value is None else str(value)

    def _chunk_sort_key(self, payload: dict[str, Any]) -> tuple[int, int, int, int, int, int, str]:
        chunk_role = str(payload.get("chunk_role") or "").lower()
        role_rank = 1 if chunk_role == "summary" else 0

        def as_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except Exception:
                return default

        page_start = as_int(payload.get("page_start"), 0)
        section_index = as_int(payload.get("section_index"), 0)
        chunk_index = as_int(payload.get("chunk_index"), 0)
        paragraph_index = as_int(payload.get("paragraph_index"), 0)
        paragraph_chunk_index = as_int(payload.get("paragraph_chunk_index"), chunk_index)
        section_title = str(payload.get("section_path_text") or payload.get("source_title") or "")
        return (role_rank, page_start, section_index, paragraph_index, paragraph_chunk_index, chunk_index, section_title)

    def _build_filter(
        self,
        doc_types: Sequence[str] | None = None,
        ticker: str | None = None,
        publish_date: str | None = None,
        chunk_roles: Sequence[str] | None = None,
        period_end: str | None = None,
        report_type: str | None = None,
        statement_type: str | None = None,
    ):
        must: list[Any] = []
        if doc_types:
            normalized = self._normalize_doc_types(doc_types)
            if len(normalized) == 1:
                must.append(
                    qdrant_models.FieldCondition(
                        key="doc_type",
                        match=qdrant_models.MatchValue(value=normalized[0]),
                    )
                )
            elif normalized:
                must.append(
                    qdrant_models.FieldCondition(
                        key="doc_type",
                        match=qdrant_models.MatchAny(any=normalized),
                    )
                )
        if ticker:
            must.append(
                qdrant_models.FieldCondition(
                    key="ticker",
                    match=qdrant_models.MatchValue(value=ticker.strip().upper()),
                )
            )
        if publish_date:
            compact_date = publish_date.strip().replace("-", "")
            if compact_date:
                must.append(
                    qdrant_models.FieldCondition(
                        key="publish_date",
                        match=qdrant_models.MatchValue(value=compact_date),
                    )
                )
        if period_end:
            compact_period_end = period_end.strip().replace("-", "")
            if compact_period_end:
                must.append(
                    qdrant_models.FieldCondition(
                        key="period_end",
                        match=qdrant_models.MatchValue(value=compact_period_end),
                    )
                )
        if report_type:
            normalized_report_type = self._normalize_report_type(report_type) or report_type.strip().lower()
            if normalized_report_type:
                must.append(
                    qdrant_models.FieldCondition(
                        key="report_type",
                        match=qdrant_models.MatchValue(value=normalized_report_type),
                    )
                )
        if statement_type:
            normalized_statement_type = self._normalize_statement_type(statement_type) or statement_type.strip().lower()
            if normalized_statement_type:
                must.append(
                    qdrant_models.FieldCondition(
                        key="statement_type",
                        match=qdrant_models.MatchValue(value=normalized_statement_type),
                    )
                )
        if chunk_roles:
            normalized_roles = [str(item).strip().lower() for item in chunk_roles if str(item).strip()]
            if len(normalized_roles) == 1:
                must.append(
                    qdrant_models.FieldCondition(
                        key="chunk_role",
                        match=qdrant_models.MatchValue(value=normalized_roles[0]),
                    )
                )
            elif normalized_roles:
                must.append(
                    qdrant_models.FieldCondition(
                        key="chunk_role",
                        match=qdrant_models.MatchAny(any=normalized_roles),
                    )
                )

        if not must:
            return None
        return qdrant_models.Filter(must=must)
