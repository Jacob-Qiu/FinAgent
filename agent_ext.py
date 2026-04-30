"""Extension-layer entrypoint that lives next to, but does not modify, legacy code."""

from __future__ import annotations

import argparse

from data_pipeline.market_data import HistoricalMarketDataPipeline
from data_pipeline.settings import load_extension_settings
from data_pipeline.universe import load_universe, select_entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FinAgent extension-layer entrypoint.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("show-config", help="Print the resolved extension settings.")
    subparsers.add_parser("show-universe", help="Print the configured stock universe.")

    history_parser = subparsers.add_parser("build-history", help="Build historical market-data assets.")
    history_parser.add_argument("--market", choices=["all", "us", "cn", "hk"], default="all")
    history_parser.add_argument("--interval", choices=["daily", "weekly", "all"], default="all")
    history_parser.add_argument("--symbols", default="")
    history_parser.add_argument("--start-date", default="2018-01-01")
    history_parser.add_argument("--end-date", default=None)
    history_parser.add_argument("--refresh-mode", choices=["incremental", "full"], default="incremental")

    kb_build_parser = subparsers.add_parser("build-kb", help="Chunk KB sources and store them in Qdrant.")
    kb_build_parser.add_argument("--doc-types", default="report,filing,encyclopedia,glossary")
    kb_build_parser.add_argument("--rebuild", action="store_true")

    kb_search_parser = subparsers.add_parser("search-kb", help="Search the Qdrant knowledge base.")
    kb_search_parser.add_argument("--query", required=True)
    kb_search_parser.add_argument("--top-k", type=int, default=5)
    kb_search_parser.add_argument("--doc-types", default="")
    kb_search_parser.add_argument("--ticker", default="")
    kb_search_parser.add_argument("--period-end", default="")
    kb_search_parser.add_argument("--report-type", default="")
    kb_search_parser.add_argument("--statement-type", default="")
    kb_search_parser.add_argument("--chunk-roles", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_extension_settings()

    if args.command == "show-config":
        print(f"default_llm_provider={settings.llm.default_provider}")
        print(f"gemini_model={settings.llm.gemini_model}")
        print(f"ollama_model={settings.llm.ollama_model}")
        print(f"market_data_dir={settings.storage.market_data_dir}")
        print(f"kb_dir={settings.storage.kb_dir}")
        print(f"kb_raw_reports_dir={settings.knowledge_base.raw_reports_dir}")
        print(f"kb_raw_filings_dir={settings.knowledge_base.raw_filings_dir}")
        print(f"kb_raw_encyclopedia_dir={settings.knowledge_base.raw_encyclopedia_dir}")
        print(f"kb_raw_glossary_dir={settings.knowledge_base.raw_glossary_dir}")
        print(f"qdrant_path={settings.knowledge_base.qdrant_path}")
        print(f"qdrant_url={settings.knowledge_base.qdrant_url}")
        print(f"qdrant_collection={settings.knowledge_base.collection_name}")
        print(f"kb_embedding_model={settings.knowledge_base.embedding_model}")
        print(f"kb_embedding_batch_size={settings.knowledge_base.embedding_batch_size}")
        print(f"kb_report_chunk_tokens={settings.knowledge_base.report_chunk_tokens}")
        print(f"kb_filing_chunk_tokens={settings.knowledge_base.filing_chunk_tokens}")
        print(f"kb_encyclopedia_chunk_tokens={settings.knowledge_base.encyclopedia_chunk_tokens}")
        print(f"kb_glossary_chunk_tokens={settings.knowledge_base.glossary_chunk_tokens}")
        return 0

    if args.command == "show-universe":
        for entry in load_universe():
            print(f"{entry.market}:{entry.symbol} {entry.name} [{entry.theme}]")
        return 0

    if args.command == "build-history":
        intervals = ["daily", "weekly"] if args.interval == "all" else [args.interval]
        symbols = {item.strip().upper() for item in args.symbols.split(",") if item.strip()}
        entries = select_entries(load_universe(), market=args.market, symbols=symbols or None)
        pipeline = HistoricalMarketDataPipeline(settings=settings)
        results = pipeline.build_universe(
            entries=entries,
            intervals=intervals,
            start_date=args.start_date,
            end_date=args.end_date,
            refresh_mode=args.refresh_mode,
        )
        for result in results:
            print(
                f"{result.market}:{result.symbol} {result.interval} "
                f"rows={result.rows} provider={result.provider} path={result.path}"
            )
        return 0

    if args.command == "build-kb":
        from data_pipeline.knowledge_base import KnowledgeBasePipeline

        pipeline = KnowledgeBasePipeline(settings=settings)
        doc_types = [item.strip() for item in args.doc_types.split(",") if item.strip()]
        summary = pipeline.build_collection(doc_types=doc_types or None, rebuild=args.rebuild)
        print(f"collection={summary.collection_name}")
        print(f"total_chunks={summary.total_chunks}")
        print(f"chunks_by_doc_type={summary.chunks_by_doc_type}")
        print(f"files_by_doc_type={summary.files_by_doc_type}")
        print(f"skipped_files={summary.skipped_files}")
        return 0

    if args.command == "search-kb":
        from data_pipeline.knowledge_base import KnowledgeBasePipeline

        pipeline = KnowledgeBasePipeline(settings=settings)
        doc_types = [item.strip() for item in args.doc_types.split(",") if item.strip()]
        hits = pipeline.search(
            query=args.query,
            top_k=args.top_k,
            doc_types=doc_types or None,
            ticker=args.ticker or None,
            chunk_roles=[item.strip() for item in args.chunk_roles.split(",") if item.strip()] or None,
            period_end=args.period_end or None,
            report_type=args.report_type or None,
            statement_type=args.statement_type or None,
        )
        for hit in hits:
            title = str(hit.payload.get("source_title") or hit.payload.get("term") or hit.payload.get("file_name") or hit.id)
            chunk_role = str(hit.payload.get("chunk_role") or "")
            source_hash = str(hit.payload.get("source_hash") or "")
            section_path = str(hit.payload.get("section_path_text") or "")
            period_end = str(hit.payload.get("period_end") or "")
            report_type = str(hit.payload.get("report_type") or "")
            statement_type = str(hit.payload.get("statement_type") or "")
            vector_score = hit.payload.get("vector_score")
            lexical_score = hit.payload.get("lexical_score")
            fused_score = hit.payload.get("fused_score")
            rerank_score = hit.payload.get("rerank_score")
            print(f"score={hit.score:.4f} id={hit.id} title={title} chunk_role={chunk_role}")
            if vector_score is not None:
                print(f"vector_score={vector_score}")
            if lexical_score is not None:
                print(f"lexical_score={lexical_score}")
            if fused_score is not None:
                print(f"fused_score={fused_score}")
            if rerank_score is not None:
                print(f"rerank_score={rerank_score}")
            if source_hash:
                print(f"source_hash={source_hash}")
            if period_end:
                print(f"period_end={period_end}")
            if report_type:
                print(f"report_type={report_type}")
            if statement_type:
                print(f"statement_type={statement_type}")
            if section_path:
                print(f"section_path={section_path}")
            print(f"content={hit.content[:300]}")
            print(f"payload={hit.payload}")
            print("-" * 80)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
