"""CLI to build and query the Qdrant-backed financial knowledge base."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from data_pipeline.settings import load_extension_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or search the Qdrant knowledge base.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Chunk sources and store them in Qdrant.")
    build_parser.add_argument(
        "--doc-types",
        default="report,filing,encyclopedia,glossary",
        help="Comma-separated doc types to ingest.",
    )
    build_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and recreate the Qdrant collection before ingesting.",
    )

    search_parser = subparsers.add_parser("search", help="Search the Qdrant knowledge base.")
    search_parser.add_argument("--query", required=True, help="Query text.")
    search_parser.add_argument("--top-k", type=int, default=5, help="Number of hits to return.")
    search_parser.add_argument(
        "--doc-types",
        default="",
        help="Optional comma-separated doc types to filter on.",
    )
    search_parser.add_argument("--ticker", default="", help="Optional ticker filter.")
    search_parser.add_argument("--period-end", default="", help="Optional filing period-end filter, e.g. 20231231.")
    search_parser.add_argument("--report-type", default="", help="Optional filing report type, e.g. annual_report.")
    search_parser.add_argument("--statement-type", default="", help="Optional filing statement type, e.g. income_statement.")
    search_parser.add_argument(
        "--chunk-roles",
        default="",
        help="Optional comma-separated chunk roles to filter on.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_extension_settings()

    if args.command == "build":
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

    if args.command == "search":
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
