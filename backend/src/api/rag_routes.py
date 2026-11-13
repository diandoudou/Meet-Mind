"""RAG API request/response models and route handlers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from rag.indexer import index_meeting, index_pdf, index_research_pdf
from rag.models import IndexResult, RagChatResponse, SearchResult
from rag.rag_chain import rag_chat
from rag.retriever import search_knowledge


class RagSearchRequest(BaseModel):
    query: str
    owner_uid: str
    project_id: Optional[str] = None
    project_name: str = ""
    top_k: int = 10


class RagSearchResponse(BaseModel):
    results: List[SearchResult]


class RagChatRequest(BaseModel):
    message: str
    owner_uid: str
    project_id: str = ""
    project_name: str = ""
    top_k: int = 6


class RagIndexMeetingRequest(BaseModel):
    owner_uid: str
    project_id: str
    meeting_id: str
    meeting_title: str
    transcript: List[Dict[str, Any]]
    summary_structured: Optional[Dict[str, Any]] = None


class RagIndexPdfRequest(BaseModel):
    owner_uid: str
    project_id: str
    file_id: str
    file_title: str
    text: str


class RagIndexResponse(BaseModel):
    indexed_chunks: int
    skipped_duplicates: int
    source_id: str
    parser: str = ""


def handle_rag_search(request: RagSearchRequest) -> RagSearchResponse:
    results = search_knowledge(
        request.query,
        owner_uid=request.owner_uid,
        project_id=request.project_id,
        project_name=request.project_name,
        top_k=request.top_k,
    )
    return RagSearchResponse(results=results)


def handle_rag_chat(request: RagChatRequest) -> RagChatResponse:
    return rag_chat(
        request.message,
        owner_uid=request.owner_uid,
        project_id=request.project_id,
        project_name=request.project_name,
        top_k=request.top_k,
    )


def handle_index_meeting(request: RagIndexMeetingRequest) -> RagIndexResponse:
    result: IndexResult = index_meeting(
        owner_uid=request.owner_uid,
        project_id=request.project_id,
        meeting_id=request.meeting_id,
        meeting_title=request.meeting_title,
        transcript=request.transcript,
        summary_structured=request.summary_structured,
    )
    return RagIndexResponse(
        indexed_chunks=result.indexed_chunks,
        skipped_duplicates=result.skipped_duplicates,
        source_id=result.source_id,
        parser=result.parser,
    )


def handle_index_pdf(request: RagIndexPdfRequest) -> RagIndexResponse:
    result: IndexResult = index_pdf(
        owner_uid=request.owner_uid,
        project_id=request.project_id,
        file_id=request.file_id,
        file_title=request.file_title,
        text=request.text,
    )
    return RagIndexResponse(
        indexed_chunks=result.indexed_chunks,
        skipped_duplicates=result.skipped_duplicates,
        source_id=result.source_id,
        parser=result.parser,
    )


def handle_index_research_pdf(
    *,
    owner_uid: str,
    project_id: str,
    file_id: str,
    file_title: str,
    pdf_path: str,
) -> RagIndexResponse:
    result: IndexResult = index_research_pdf(
        owner_uid=owner_uid,
        project_id=project_id,
        file_id=file_id,
        file_title=file_title,
        pdf_path=pdf_path,
    )
    return RagIndexResponse(
        indexed_chunks=result.indexed_chunks,
        skipped_duplicates=result.skipped_duplicates,
        source_id=result.source_id,
        parser=result.parser,
    )
