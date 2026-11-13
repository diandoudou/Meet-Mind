"""Hybrid retrieval: vector (optionally multimodal) + keyword RRF."""

from __future__ import annotations

import os
import re
from typing import List, Optional

import jieba

from rag.models import SearchResult
from rag.vector_store import get_vector_store


def _tokenize(text: str) -> List[str]:
    text = text.lower()
    latin = re.findall(r"[a-z0-9]+", text)
    cjk = [t.strip() for t in jieba.cut(text) if len(t.strip()) > 1]
    return latin + cjk


def _keyword_score(query: str, document: str) -> float:
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0
    doc_tokens = set(_tokenize(document))
    if not doc_tokens:
        return 0.0
    overlap = len(query_tokens & doc_tokens)
    return overlap / len(query_tokens)


def _rrf_merge(
    vector_results: List[dict],
    keyword_scores: dict[str, float],
    k: int = 60,
) -> List[dict]:
    ranks: dict[str, float] = {}

    for rank, item in enumerate(vector_results, start=1):
        chunk_id = item["chunk_id"]
        ranks[chunk_id] = ranks.get(chunk_id, 0.0) + 1.0 / (k + rank)

    sorted_kw = sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (chunk_id, score) in enumerate(sorted_kw, start=1):
        if score <= 0:
            continue
        ranks[chunk_id] = ranks.get(chunk_id, 0.0) + 1.0 / (k + rank)

    merged = {item["chunk_id"]: item for item in vector_results}
    ordered_ids = sorted(ranks.keys(), key=lambda cid: ranks[cid], reverse=True)
    return [merged[cid] for cid in ordered_ids if cid in merged]


def _citation_label_for(meta: dict, index: int) -> str:
    modality = meta.get("modality") or "text"
    figure_id = meta.get("figure_id") or ""
    page = meta.get("page_number") or 0
    if modality == "image" and figure_id:
        return f"[{index}:{figure_id}]"
    if page:
        return f"[{index}:p{page}]"
    return f"[{index}]"


def search_knowledge(
    query: str,
    *,
    owner_uid: str,
    project_id: Optional[str] = None,
    project_name: str = "",
    top_k: Optional[int] = None,
    modality: Optional[str] = None,
) -> List[SearchResult]:
    if not query.strip() or not owner_uid:
        return []

    top_k = top_k or int(os.getenv("RAG_TOP_K", "8"))
    store = get_vector_store()
    fetch_k = max(top_k * 2, 10)

    # Prefer multi-vector hybrid when Milvus is configured
    if hasattr(store, "hybrid_search") and os.getenv("RAG_VECTOR_STORE", "chroma").lower() == "milvus":
        vector_hits = store.hybrid_search(
            query,
            owner_uid=owner_uid,
            project_id=project_id,
            top_k=fetch_k,
        )
    else:
        vector_hits = store.search(
            query,
            owner_uid=owner_uid,
            project_id=project_id,
            top_k=fetch_k,
            modality=modality,
        )

    if modality:
        vector_hits = [
            h for h in vector_hits if (h.get("metadata") or {}).get("modality", "text") == modality
        ]

    keyword_scores = {
        hit["chunk_id"]: _keyword_score(query, hit["text"]) for hit in vector_hits
    }
    merged = _rrf_merge(vector_hits, keyword_scores)[:top_k]

    results: List[SearchResult] = []
    for index, hit in enumerate(merged, start=1):
        meta = hit["metadata"] or {}
        vector_score = float(hit.get("score", 0.0))
        kw_score = keyword_scores.get(hit["chunk_id"], 0.0)
        combined = min(1.0, 0.7 * vector_score + 0.3 * kw_score)

        start_ts = meta.get("start_ts") or None
        if start_ts == 0:
            start_ts = None

        page_number = meta.get("page_number") or None
        if page_number == 0:
            page_number = None

        results.append(
            SearchResult(
                chunk_id=hit["chunk_id"],
                score=round(combined, 4),
                text=hit["text"],
                source_type=meta.get("source_type", "meeting_transcript"),
                source_id=meta.get("source_id", ""),
                source_title=meta.get("source_title", ""),
                project_id=meta.get("project_id", project_id or ""),
                project_name=project_name,
                speaker=meta.get("speaker") or None,
                timestamp=start_ts,
                citation_label=_citation_label_for(meta, index),
                modality=meta.get("modality") or "text",
                page_number=page_number,
                section_title=meta.get("section_title") or "",
                figure_id=meta.get("figure_id") or "",
                image_path=meta.get("image_path") or "",
                caption=meta.get("caption") or "",
            )
        )
    return results
