"""In-memory / JSON-persisted vector store (no Chroma/Milvus dependency)."""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import List, Optional

from rag.embedder import embed_texts
from rag.models import KnowledgeChunk


def _store_path() -> Path:
    default = Path(__file__).resolve().parents[2] / "data" / "simple_store" / "chunks.json"
    path = Path(os.getenv("SIMPLE_STORE_PATH", str(default)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class SimpleVectorStore:
    """Lightweight dense store for local demos / evals without Chroma."""

    def __init__(self) -> None:
        self.path = _store_path()
        self._rows: List[dict] = []
        self._known_hashes: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._rows = json.loads(self.path.read_text(encoding="utf-8"))
            for row in self._rows:
                if row.get("content_hash"):
                    self._known_hashes.add(row["content_hash"])
        except Exception as exc:
            print(f"[RAG] SimpleVectorStore load failed: {exc}")
            self._rows = []

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._rows, ensure_ascii=False), encoding="utf-8")

    def upsert_chunks(self, chunks: List[KnowledgeChunk]) -> tuple[int, int]:
        if not chunks:
            return 0, 0

        pending: List[KnowledgeChunk] = []
        skipped = 0
        for chunk in chunks:
            if chunk.content_hash in self._known_hashes:
                skipped += 1
                continue
            pending.append(chunk)

        if not pending:
            return 0, skipped

        vectors = embed_texts([c.text[:8000] for c in pending])
        for chunk, vec in zip(pending, vectors):
            self._rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "embedding": vec,
                    "owner_uid": chunk.owner_uid,
                    "project_id": chunk.project_id,
                    "source_type": chunk.source_type,
                    "source_id": chunk.source_id,
                    "source_title": chunk.source_title,
                    "chunk_index": chunk.chunk_index,
                    "speaker": chunk.speaker or "",
                    "start_ts": chunk.start_ts or 0,
                    "page_number": chunk.page_number or 0,
                    "content_hash": chunk.content_hash,
                    "modality": chunk.modality,
                    "section_title": chunk.section_title or "",
                    "figure_id": chunk.figure_id or "",
                    "image_path": chunk.image_path or "",
                    "caption": chunk.caption or "",
                }
            )
            self._known_hashes.add(chunk.content_hash)

        self._save()
        return len(pending), skipped

    def delete_by_source(self, source_id: str) -> None:
        before = len(self._rows)
        self._rows = [r for r in self._rows if r.get("source_id") != source_id]
        self._known_hashes = {r.get("content_hash", "") for r in self._rows if r.get("content_hash")}
        if len(self._rows) != before:
            self._save()

    def search(
        self,
        query: str,
        *,
        owner_uid: str,
        project_id: Optional[str] = None,
        top_k: int = 10,
        modality: Optional[str] = None,
        vector_field: str = "text_vector",
    ) -> List[dict]:
        del vector_field
        if not self._rows:
            return []

        q_raw = (query or "").lower()
        q_tokens = set(re.findall(r"[a-z0-9][a-z0-9\.\-%]{1,}", q_raw))
        # drop ultra-common stopwords for keyword channel
        q_tokens -= {
            "the", "and", "for", "are", "what", "which", "how", "does", "this",
            "paper", "model", "with", "from", "that", "have", "best",
        }
        qvec = embed_texts([query])[0]
        scored: List[tuple[float, dict]] = []
        for row in self._rows:
            if row.get("owner_uid") != owner_uid:
                continue
            if project_id and row.get("project_id") != project_id:
                continue
            if modality and row.get("modality") != modality:
                continue
            dense = _cosine(qvec, row.get("embedding") or [])
            text_l = (row.get("text") or "").lower()
            if q_tokens:
                hits = sum(1 for t in q_tokens if t in text_l)
                kw = hits / len(q_tokens)
                # bonus if rare technical tokens match
                tech = [t for t in q_tokens if any(c.isdigit() for c in t) or t in {"knn", "svm", "cwt", "rms", "physionet"}]
                if tech:
                    tech_hits = sum(1 for t in tech if t in text_l)
                    kw = min(1.0, kw + 0.25 * (tech_hits / len(tech)))
            else:
                kw = 0.0
            score = 0.35 * dense + 0.65 * kw
            scored.append((score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        items: List[dict] = []
        for score, row in scored[:top_k]:
            items.append(
                {
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "score": float(score),
                    "metadata": {
                        "owner_uid": row.get("owner_uid", ""),
                        "project_id": row.get("project_id", ""),
                        "source_type": row.get("source_type", "pdf"),
                        "source_id": row.get("source_id", ""),
                        "source_title": row.get("source_title", ""),
                        "modality": row.get("modality", "text"),
                        "section_title": row.get("section_title", ""),
                        "figure_id": row.get("figure_id", ""),
                        "image_path": row.get("image_path", ""),
                        "caption": row.get("caption", ""),
                        "speaker": row.get("speaker", ""),
                        "page_number": row.get("page_number", 0),
                        "start_ts": row.get("start_ts", 0),
                        "content_hash": row.get("content_hash", ""),
                    },
                }
            )
        return items

    def hybrid_search(
        self,
        query: str,
        *,
        owner_uid: str,
        project_id: Optional[str] = None,
        top_k: int = 10,
    ) -> List[dict]:
        return self.search(
            query,
            owner_uid=owner_uid,
            project_id=project_id,
            top_k=top_k,
        )
