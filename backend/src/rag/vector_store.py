"""Vector store factory: Chroma (default) or Milvus multi-vector."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Protocol, Union

from rag.models import KnowledgeChunk


def _persist_dir() -> str:
    default = Path(__file__).resolve().parents[2] / "data" / "chroma"
    return os.getenv("CHROMA_PERSIST_DIR", str(default))


def _backend_name() -> str:
    return os.getenv("RAG_VECTOR_STORE", "chroma").strip().lower()


@lru_cache(maxsize=1)
def get_chroma_collection():
    import chromadb

    from rag.embedder import get_embedding_function

    persist_dir = _persist_dir()
    Path(persist_dir).mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=persist_dir)
    embedding_fn = get_embedding_function()
    return client.get_or_create_collection(
        name="meetmind_chunks",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


class VectorStore:
    """Chroma-backed store (text modality; multimodal metadata preserved)."""

    def __init__(self) -> None:
        self.collection = get_chroma_collection()
        self._known_hashes: set[str] = set()

    def _load_existing_hashes(self, source_id: str) -> None:
        try:
            existing = self.collection.get(where={"source_id": source_id})
            for meta in existing.get("metadatas") or []:
                if meta and meta.get("content_hash"):
                    self._known_hashes.add(meta["content_hash"])
        except Exception:
            pass

    def upsert_chunks(self, chunks: List[KnowledgeChunk]) -> tuple[int, int]:
        if not chunks:
            return 0, 0

        self._load_existing_hashes(chunks[0].source_id)

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[dict] = []

        indexed = 0
        skipped = 0

        for chunk in chunks:
            if chunk.content_hash in self._known_hashes:
                skipped += 1
                continue

            ids.append(chunk.chunk_id)
            documents.append(chunk.text)
            metadatas.append(
                {
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
                    "section_title": (chunk.section_title or "")[:500],
                    "figure_id": chunk.figure_id or "",
                    "image_path": (chunk.image_path or "")[:1000],
                    "caption": (chunk.caption or "")[:1000],
                }
            )
            self._known_hashes.add(chunk.content_hash)
            indexed += 1

        if ids:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

        return indexed, skipped

    def delete_by_source(self, source_id: str) -> None:
        try:
            self.collection.delete(where={"source_id": source_id})
        except Exception as exc:
            print(f"[RAG] delete_by_source failed: {exc}")

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
        del vector_field  # Chroma has a single embedding space
        where: dict = {"owner_uid": owner_uid}
        if project_id:
            where["project_id"] = project_id
        if modality:
            where["modality"] = modality

        try:
            result = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            print(f"[RAG] vector search failed: {exc}")
            return []

        items: List[dict] = []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
            if not meta:
                continue
            score = max(0.0, 1.0 - float(dist))
            items.append(
                {
                    "chunk_id": chunk_id,
                    "text": doc,
                    "score": score,
                    "metadata": meta,
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


class VectorStoreProtocol(Protocol):
    def upsert_chunks(self, chunks: List[KnowledgeChunk]) -> tuple[int, int]: ...

    def delete_by_source(self, source_id: str) -> None: ...

    def search(
        self,
        query: str,
        *,
        owner_uid: str,
        project_id: Optional[str] = None,
        top_k: int = 10,
        modality: Optional[str] = None,
        vector_field: str = "text_vector",
    ) -> List[dict]: ...

    def hybrid_search(
        self,
        query: str,
        *,
        owner_uid: str,
        project_id: Optional[str] = None,
        top_k: int = 10,
    ) -> List[dict]: ...


_vector_store: Optional[Union[VectorStore, object]] = None


def get_vector_store() -> VectorStoreProtocol:
    global _vector_store
    if _vector_store is not None:
        return _vector_store  # type: ignore[return-value]

    backend = _backend_name()
    if backend == "milvus":
        from rag.milvus_store import MilvusVectorStore

        _vector_store = MilvusVectorStore()
        print("[RAG] Using Milvus vector store")
    elif backend in ("simple", "memory", "json"):
        from rag.simple_store import SimpleVectorStore

        _vector_store = SimpleVectorStore()
        print("[RAG] Using SimpleVectorStore")
    else:
        try:
            _vector_store = VectorStore()
            print("[RAG] Using Chroma vector store")
        except Exception as exc:
            print(f"[RAG] Chroma unavailable ({exc}), falling back to SimpleVectorStore")
            from rag.simple_store import SimpleVectorStore

            _vector_store = SimpleVectorStore()
    return _vector_store  # type: ignore[return-value]
