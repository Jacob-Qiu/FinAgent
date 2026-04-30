"""Shared KB pipeline provider for local retrieval tools."""

from __future__ import annotations

from data_pipeline.knowledge_base import KnowledgeBasePipeline


_kb_pipeline: KnowledgeBasePipeline | None = None


def get_kb_pipeline() -> KnowledgeBasePipeline:
    """Reuse one Qdrant local client per process to avoid storage lock conflicts."""
    global _kb_pipeline
    if _kb_pipeline is None:
        _kb_pipeline = KnowledgeBasePipeline()
    return _kb_pipeline
