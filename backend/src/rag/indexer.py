"""Knowledge indexing orchestration (meetings + research PDFs)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.chunker import (
    chunk_pdf_text,
    chunk_research_document,
    chunk_summary_structured,
    chunk_transcript,
)
from rag.marker_parser import parse_research_pdf
from rag.models import IndexResult, KnowledgeChunk
from rag.vector_store import get_vector_store


def index_meeting(
    *,
    owner_uid: str,
    project_id: str,
    meeting_id: str,
    meeting_title: str,
    transcript: List[Dict[str, Any]],
    summary_structured: Optional[Dict[str, Any]] = None,
) -> IndexResult:
    if not owner_uid:
        return IndexResult(source_id=meeting_id)

    store = get_vector_store()
    store.delete_by_source(meeting_id)

    all_chunks: List[KnowledgeChunk] = []
    all_chunks.extend(
        chunk_transcript(
            transcript,
            owner_uid=owner_uid,
            project_id=project_id,
            meeting_id=meeting_id,
            meeting_title=meeting_title,
        )
    )

    if summary_structured:
        all_chunks.extend(
            chunk_summary_structured(
                summary_structured,
                owner_uid=owner_uid,
                project_id=project_id,
                meeting_id=meeting_id,
                meeting_title=meeting_title,
            )
        )

    indexed, skipped = store.upsert_chunks(all_chunks)
    print(f"[RAG] Indexed meeting {meeting_id}: {indexed} chunks, skipped {skipped}")
    return IndexResult(
        indexed_chunks=indexed,
        skipped_duplicates=skipped,
        source_id=meeting_id,
        parser="transcript",
    )


def index_pdf(
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_title: str,
    text: str,
) -> IndexResult:
    """Legacy flat-text PDF indexing (API compatibility)."""
    if not owner_uid or not text.strip():
        return IndexResult(source_id=file_id, parser="flat_text")

    store = get_vector_store()
    store.delete_by_source(file_id)

    chunks = chunk_pdf_text(
        text,
        owner_uid=owner_uid,
        project_id=project_id,
        file_id=file_id,
        file_title=file_title,
    )
    indexed, skipped = store.upsert_chunks(chunks)
    print(f"[RAG] Indexed PDF {file_id}: {indexed} chunks, skipped {skipped}")
    return IndexResult(
        indexed_chunks=indexed,
        skipped_duplicates=skipped,
        source_id=file_id,
        parser="flat_text",
    )


def index_research_pdf(
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_title: str,
    pdf_path: str,
    assets_dir: Optional[str] = None,
) -> IndexResult:
    """
    Structure-aware research PDF indexing via Marker (fallback pypdf).
    Produces section / table / figure chunks with multimodal metadata.
    """
    if not owner_uid:
        return IndexResult(source_id=file_id)

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(pdf_path)

    out_dir = assets_dir or str(path.parent / f"{path.stem}_assets")
    document = parse_research_pdf(str(path), output_dir=out_dir)

    store = get_vector_store()
    store.delete_by_source(file_id)

    chunks = chunk_research_document(
        document,
        owner_uid=owner_uid,
        project_id=project_id,
        file_id=file_id,
        file_title=file_title or document.title,
    )

    if not chunks and document.full_text.strip():
        chunks = chunk_pdf_text(
            document.full_text,
            owner_uid=owner_uid,
            project_id=project_id,
            file_id=file_id,
            file_title=file_title or document.title,
        )

    indexed, skipped = store.upsert_chunks(chunks)
    print(
        f"[RAG] Indexed research PDF {file_id} via {document.parser}: "
        f"{indexed} chunks, skipped {skipped}"
    )
    return IndexResult(
        indexed_chunks=indexed,
        skipped_duplicates=skipped,
        source_id=file_id,
        parser=document.parser,
    )
