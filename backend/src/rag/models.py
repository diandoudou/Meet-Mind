"""RAG data models (text + multimodal paper chunks)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal[
    "meeting_transcript",
    "meeting_summary",
    "pdf",
    "paper_section",
    "paper_table",
    "paper_figure",
    "action_item",
]

Modality = Literal["text", "image", "table"]


class KnowledgeChunk(BaseModel):
    chunk_id: str
    text: str
    owner_uid: str
    project_id: str
    source_type: SourceType
    source_id: str
    source_title: str
    chunk_index: int = 0
    speaker: Optional[str] = None
    start_ts: Optional[int] = None
    page_number: Optional[int] = None
    content_hash: str = ""
    modality: Modality = "text"
    section_title: str = ""
    figure_id: str = ""
    image_path: str = ""
    caption: str = ""


class SearchResult(BaseModel):
    chunk_id: str
    score: float
    text: str
    source_type: SourceType
    source_id: str
    source_title: str
    project_id: str
    project_name: str = ""
    speaker: Optional[str] = None
    timestamp: Optional[int] = None
    citation_label: str = ""
    modality: Modality = "text"
    page_number: Optional[int] = None
    section_title: str = ""
    figure_id: str = ""
    image_path: str = ""
    caption: str = ""


class RagCitation(BaseModel):
    label: str
    chunk_id: str
    source_type: SourceType
    source_id: str
    source_title: str
    excerpt: str
    url_path: str = ""
    page_number: Optional[int] = None
    figure_id: str = ""
    image_path: str = ""
    modality: Modality = "text"


class RagChatResponse(BaseModel):
    answer: str
    citations: list[RagCitation] = Field(default_factory=list)
    retrieval_meta: dict = Field(default_factory=dict)


class IndexResult(BaseModel):
    indexed_chunks: int = 0
    skipped_duplicates: int = 0
    source_id: str = ""
    parser: str = ""
