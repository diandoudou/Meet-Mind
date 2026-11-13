"""Document chunking for meetings and research papers (LangChain semantic split)."""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from rag.marker_parser import ParsedBlock, ParsedDocument
from rag.models import KnowledgeChunk, Modality, SourceType


def _hash_content(source_id: str, chunk_index: int, text: str) -> str:
    raw = f"{source_id}:{chunk_index}:{text.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fixed_split(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def _get_semantic_embeddings():
    """LangChain embeddings used by SemanticChunker (prefer Gemini)."""
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("RAG_EMBEDDING_MODEL", "models/text-embedding-004")
    if not api_key:
        return None
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key)


def _semantic_split(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """
    LangChain SemanticChunker: split on embedding similarity breakpoints.
    Falls back to fixed-size window if experimental package / embeddings unavailable.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    if os.getenv("RAG_CHUNK_STRATEGY", "semantic").lower() in ("fixed", "window"):
        return _fixed_split(text, chunk_size, overlap)

    try:
        from langchain_experimental.text_splitter import SemanticChunker
    except Exception as exc:
        print(f"[RAG] SemanticChunker unavailable, using fixed split: {exc}")
        return _fixed_split(text, chunk_size, overlap)

    embeddings = _get_semantic_embeddings()
    if embeddings is None:
        return _fixed_split(text, chunk_size, overlap)

    try:
        threshold = os.getenv("RAG_SEMANTIC_BREAKPOINT", "percentile")
        splitter = SemanticChunker(
            embeddings,
            breakpoint_threshold_type=threshold,  # percentile | standard_deviation | interquartile | gradient
        )
        parts = splitter.split_text(text)
        parts = [p.strip() for p in parts if p and p.strip()]
        if not parts:
            return _fixed_split(text, chunk_size, overlap)

        # SemanticChunker may still emit oversized chunks — re-window those only
        final: List[str] = []
        max_chars = int(os.getenv("RAG_SEMANTIC_MAX_CHARS", str(chunk_size * 3)))
        for part in parts:
            if len(part) <= max_chars:
                final.append(part)
            else:
                final.extend(_fixed_split(part, chunk_size, overlap))
        return final
    except Exception as exc:
        print(f"[RAG] SemanticChunker failed, using fixed split: {exc}")
        return _fixed_split(text, chunk_size, overlap)


def _split_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    return _semantic_split(text, chunk_size, overlap)


def _make_chunk(
    *,
    text: str,
    owner_uid: str,
    project_id: str,
    source_type: SourceType,
    source_id: str,
    source_title: str,
    chunk_index: int,
    speaker: Optional[str] = None,
    start_ts: Optional[int] = None,
    page_number: Optional[int] = None,
    modality: Modality = "text",
    section_title: str = "",
    figure_id: str = "",
    image_path: str = "",
    caption: str = "",
) -> KnowledgeChunk:
    content_hash = _hash_content(source_id, chunk_index, text)
    return KnowledgeChunk(
        chunk_id=str(uuid.uuid4()),
        text=text,
        owner_uid=owner_uid,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        source_title=source_title,
        chunk_index=chunk_index,
        speaker=speaker,
        start_ts=start_ts,
        page_number=page_number,
        content_hash=content_hash,
        modality=modality,
        section_title=section_title,
        figure_id=figure_id,
        image_path=image_path,
        caption=caption,
    )


def chunk_transcript(
    transcript: List[Dict[str, Any]],
    *,
    owner_uid: str,
    project_id: str,
    meeting_id: str,
    meeting_title: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[KnowledgeChunk]:
    chunks: List[KnowledgeChunk] = []
    buffer_speaker: Optional[str] = None
    buffer_text: List[str] = []
    buffer_ts: Optional[int] = None
    chunk_index = 0

    def flush_buffer() -> None:
        nonlocal chunk_index
        if not buffer_text:
            return
        combined = " ".join(buffer_text).strip()
        for part in _split_text(combined, chunk_size, overlap):
            chunks.append(
                _make_chunk(
                    text=f"{buffer_speaker or 'Speaker'}: {part}",
                    owner_uid=owner_uid,
                    project_id=project_id,
                    source_type="meeting_transcript",
                    source_id=meeting_id,
                    source_title=meeting_title,
                    chunk_index=chunk_index,
                    speaker=buffer_speaker,
                    start_ts=buffer_ts,
                    modality="text",
                )
            )
            chunk_index += 1
        buffer_text.clear()

    for entry in transcript:
        speaker = entry.get("speaker") or "Speaker"
        text = (entry.get("text") or "").strip()
        if not text:
            continue

        ts = entry.get("timestamp")
        if isinstance(ts, str):
            try:
                from datetime import datetime

                ts = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
            except Exception:
                ts = None
        elif isinstance(ts, (int, float)):
            ts = int(ts)

        if buffer_speaker and buffer_speaker != speaker and buffer_text:
            flush_buffer()

        buffer_speaker = speaker
        if buffer_ts is None and ts is not None:
            buffer_ts = ts
        buffer_text.append(text)

        if sum(len(t) for t in buffer_text) >= chunk_size:
            flush_buffer()
            buffer_ts = ts

    flush_buffer()
    return chunks


def chunk_summary_structured(
    summary: Dict[str, Any],
    *,
    owner_uid: str,
    project_id: str,
    meeting_id: str,
    meeting_title: str,
) -> List[KnowledgeChunk]:
    chunks: List[KnowledgeChunk] = []
    chunk_index = 0
    title = summary.get("title") or meeting_title

    def add(text: str) -> None:
        nonlocal chunk_index
        chunks.append(
            _make_chunk(
                text=text,
                owner_uid=owner_uid,
                project_id=project_id,
                source_type="meeting_summary",
                source_id=meeting_id,
                source_title=title,
                chunk_index=chunk_index,
                modality="text",
            )
        )
        chunk_index += 1

    if summary.get("overview"):
        add(f"会议概要: {summary['overview']}")

    for topic in summary.get("topics") or []:
        points = topic.get("discussion_points") or []
        conclusion = topic.get("conclusion") or ""
        text = f"议题: {topic.get('title', '')}\n" + "\n".join(f"- {p}" for p in points)
        if conclusion:
            text += f"\n结论: {conclusion}"
        add(text.strip())

    for decision in summary.get("decisions") or []:
        add(f"会议决策: {decision}")

    for step in summary.get("next_steps") or []:
        add(f"下一步: {step}")

    return chunks


def chunk_pdf_text(
    text: str,
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_title: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[KnowledgeChunk]:
    """Legacy flat PDF chunking (compatibility)."""
    chunks: List[KnowledgeChunk] = []
    for index, part in enumerate(_split_text(text, chunk_size, overlap)):
        chunks.append(
            _make_chunk(
                text=part,
                owner_uid=owner_uid,
                project_id=project_id,
                source_type="pdf",
                source_id=file_id,
                source_title=file_title,
                chunk_index=index,
                modality="text",
            )
        )
    return chunks


def _block_to_source_type(block: ParsedBlock) -> SourceType:
    if block.block_type == "figure":
        return "paper_figure"
    if block.block_type == "table":
        return "paper_table"
    if block.block_type in ("section", "paragraph"):
        return "paper_section"
    return "pdf"


def chunk_research_document(
    document: ParsedDocument,
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_title: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> List[KnowledgeChunk]:
    """
    Structure-aware chunking for Marker/pypdf parsed research papers.
    - sections/paragraphs: keep semantic blocks, slide-window if too long
    - tables: one chunk per table
    - figures: one chunk with caption (+ image path); modality=image
    """
    chunks: List[KnowledgeChunk] = []
    chunk_index = 0
    title = file_title or document.title

    for block in document.blocks:
        source_type = _block_to_source_type(block)

        if block.block_type == "figure":
            caption = block.caption or block.text
            searchable = (
                f"[FIGURE {block.figure_id or ''}] "
                f"section={block.section_title} "
                f"caption={caption}"
            ).strip()
            chunks.append(
                _make_chunk(
                    text=searchable,
                    owner_uid=owner_uid,
                    project_id=project_id,
                    source_type="paper_figure",
                    source_id=file_id,
                    source_title=title,
                    chunk_index=chunk_index,
                    page_number=block.page_number,
                    modality="image",
                    section_title=block.section_title,
                    figure_id=block.figure_id,
                    image_path=block.image_path,
                    caption=caption,
                )
            )
            chunk_index += 1
            continue

        if block.block_type == "table":
            chunks.append(
                _make_chunk(
                    text=f"[TABLE] section={block.section_title}\n{block.text}",
                    owner_uid=owner_uid,
                    project_id=project_id,
                    source_type="paper_table",
                    source_id=file_id,
                    source_title=title,
                    chunk_index=chunk_index,
                    page_number=block.page_number,
                    modality="table",
                    section_title=block.section_title,
                )
            )
            chunk_index += 1
            continue

        # section title alone is short; keep as its own chunk for navigation
        if block.block_type == "section":
            chunks.append(
                _make_chunk(
                    text=f"[SECTION] {block.text}",
                    owner_uid=owner_uid,
                    project_id=project_id,
                    source_type="paper_section",
                    source_id=file_id,
                    source_title=title,
                    chunk_index=chunk_index,
                    page_number=block.page_number,
                    modality="text",
                    section_title=block.section_title or block.text,
                )
            )
            chunk_index += 1
            continue

        prefix = f"section={block.section_title}\n" if block.section_title else ""
        for part in _split_text(prefix + block.text, chunk_size, overlap):
            chunks.append(
                _make_chunk(
                    text=part,
                    owner_uid=owner_uid,
                    project_id=project_id,
                    source_type=source_type,
                    source_id=file_id,
                    source_title=title,
                    chunk_index=chunk_index,
                    page_number=block.page_number,
                    modality="text",
                    section_title=block.section_title,
                )
            )
            chunk_index += 1

    return chunks
