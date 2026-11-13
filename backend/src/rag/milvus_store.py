"""Milvus (Lite) multi-vector store: text embeddings + Chinese-CLIP image channel."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from rag.chinese_clip import (
    build_image_vectors_for_chunks,
    chinese_clip_dim,
    embed_texts_chinese_clip,
)
from rag.embedder import embed_texts
from rag.models import KnowledgeChunk


def _milvus_uri() -> str:
    default = Path(__file__).resolve().parents[2] / "data" / "milvus" / "meetmind.db"
    path = Path(os.getenv("MILVUS_URI", str(default)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def _collection_name() -> str:
    # v2: separate text_dim / chinese-clip image_dim
    return os.getenv("MILVUS_COLLECTION", "meetmind_chunks_v2")


class MilvusVectorStore:
    """
    Multi-vector store:
    - text_vector: Gemini / default text embedding
    - image_vector: Chinese-CLIP (中文 CLIP) — real image encode when path exists;
      otherwise CLIP text encode of caption/body for aligned search space
    """

    def __init__(self) -> None:
        from pymilvus import DataType, MilvusClient

        self._MilvusClient = MilvusClient
        self._DataType = DataType
        self.client = MilvusClient(uri=_milvus_uri())
        self.collection = _collection_name()
        self._text_dim: Optional[int] = None
        self._image_dim: Optional[int] = None
        self._known_hashes: set[str] = set()
        self._ensure_collection()

    def _detect_text_dim(self) -> int:
        if self._text_dim:
            return self._text_dim
        probe = embed_texts(["dimension probe"])[0]
        self._text_dim = len(probe)
        return self._text_dim

    def _detect_image_dim(self) -> int:
        if self._image_dim:
            return self._image_dim
        self._image_dim = chinese_clip_dim()
        return self._image_dim

    def _ensure_collection(self) -> None:
        if self.client.has_collection(self.collection):
            return

        text_dim = self._detect_text_dim()
        image_dim = self._detect_image_dim()
        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(field_name="chunk_id", datatype=self._DataType.VARCHAR, is_primary=True, max_length=64)
        schema.add_field(field_name="text_vector", datatype=self._DataType.FLOAT_VECTOR, dim=text_dim)
        schema.add_field(field_name="image_vector", datatype=self._DataType.FLOAT_VECTOR, dim=image_dim)
        schema.add_field(field_name="text", datatype=self._DataType.VARCHAR, max_length=60000)
        schema.add_field(field_name="owner_uid", datatype=self._DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="project_id", datatype=self._DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="source_type", datatype=self._DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="source_id", datatype=self._DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="source_title", datatype=self._DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="modality", datatype=self._DataType.VARCHAR, max_length=32)
        schema.add_field(field_name="section_title", datatype=self._DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="figure_id", datatype=self._DataType.VARCHAR, max_length=64)
        schema.add_field(field_name="image_path", datatype=self._DataType.VARCHAR, max_length=1024)
        schema.add_field(field_name="caption", datatype=self._DataType.VARCHAR, max_length=4000)
        schema.add_field(field_name="speaker", datatype=self._DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="content_hash", datatype=self._DataType.VARCHAR, max_length=128)
        schema.add_field(field_name="chunk_index", datatype=self._DataType.INT64)
        schema.add_field(field_name="page_number", datatype=self._DataType.INT64)
        schema.add_field(field_name="start_ts", datatype=self._DataType.INT64)

        index_params = self.client.prepare_index_params()
        index_params.add_index(field_name="text_vector", index_type="AUTOINDEX", metric_type="COSINE")
        index_params.add_index(field_name="image_vector", index_type="AUTOINDEX", metric_type="COSINE")

        self.client.create_collection(
            collection_name=self.collection,
            schema=schema,
            index_params=index_params,
        )
        print(
            f"[RAG] Created Milvus collection '{self.collection}' "
            f"text_dim={text_dim} chinese_clip_dim={image_dim}"
        )

    def _load_existing_hashes(self, source_id: str) -> None:
        try:
            rows = self.client.query(
                collection_name=self.collection,
                filter=f'source_id == "{source_id}"',
                output_fields=["content_hash"],
                limit=16384,
            )
            for row in rows:
                if row.get("content_hash"):
                    self._known_hashes.add(row["content_hash"])
        except Exception:
            pass

    def upsert_chunks(self, chunks: List[KnowledgeChunk]) -> tuple[int, int]:
        if not chunks:
            return 0, 0

        self._ensure_collection()
        self._load_existing_hashes(chunks[0].source_id)

        pending: List[KnowledgeChunk] = []
        skipped = 0
        for chunk in chunks:
            if chunk.content_hash in self._known_hashes:
                skipped += 1
                continue
            pending.append(chunk)

        if not pending:
            return 0, skipped

        texts = [c.text[:59000] for c in pending]
        text_vectors = embed_texts(texts)
        image_vectors = build_image_vectors_for_chunks(
            modalities=[c.modality for c in pending],
            image_paths=[c.image_path or "" for c in pending],
            captions=[c.caption or "" for c in pending],
            texts=texts,
        )

        rows = []
        for chunk, tv, iv in zip(pending, text_vectors, image_vectors):
            rows.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text_vector": tv,
                    "image_vector": iv,
                    "text": chunk.text[:59000],
                    "owner_uid": chunk.owner_uid,
                    "project_id": chunk.project_id,
                    "source_type": chunk.source_type,
                    "source_id": chunk.source_id,
                    "source_title": (chunk.source_title or "")[:500],
                    "modality": chunk.modality,
                    "section_title": (chunk.section_title or "")[:500],
                    "figure_id": chunk.figure_id or "",
                    "image_path": (chunk.image_path or "")[:1000],
                    "caption": (chunk.caption or "")[:3900],
                    "speaker": chunk.speaker or "",
                    "content_hash": chunk.content_hash,
                    "chunk_index": int(chunk.chunk_index),
                    "page_number": int(chunk.page_number or 0),
                    "start_ts": int(chunk.start_ts or 0),
                }
            )
            self._known_hashes.add(chunk.content_hash)

        self.client.upsert(collection_name=self.collection, data=rows)
        return len(rows), skipped

    def delete_by_source(self, source_id: str) -> None:
        try:
            self.client.delete(
                collection_name=self.collection,
                filter=f'source_id == "{source_id}"',
            )
        except Exception as exc:
            print(f"[RAG] Milvus delete_by_source failed: {exc}")

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
        self._ensure_collection()

        if vector_field == "image_vector":
            query_vec = embed_texts_chinese_clip([query])[0]
        else:
            query_vec = embed_texts([query])[0]

        filters = [f'owner_uid == "{owner_uid}"']
        if project_id:
            filters.append(f'project_id == "{project_id}"')
        if modality:
            filters.append(f'modality == "{modality}"')
        expr = " and ".join(filters)

        try:
            results = self.client.search(
                collection_name=self.collection,
                data=[query_vec],
                anns_field=vector_field,
                limit=top_k,
                filter=expr,
                output_fields=[
                    "text",
                    "owner_uid",
                    "project_id",
                    "source_type",
                    "source_id",
                    "source_title",
                    "modality",
                    "section_title",
                    "figure_id",
                    "image_path",
                    "caption",
                    "speaker",
                    "page_number",
                    "start_ts",
                    "content_hash",
                ],
            )
        except Exception as exc:
            print(f"[RAG] Milvus search failed: {exc}")
            return []

        items: List[dict] = []
        for hit in results[0] if results else []:
            entity = hit.get("entity") or {}
            score = hit.get("distance")
            if score is None:
                score = hit.get("score", 0.0)
            score = float(score)
            if score < 0:
                score = 1.0 + score
            items.append(
                {
                    "chunk_id": hit.get("id") or entity.get("chunk_id"),
                    "text": entity.get("text", ""),
                    "score": score,
                    "metadata": {
                        "owner_uid": entity.get("owner_uid", ""),
                        "project_id": entity.get("project_id", ""),
                        "source_type": entity.get("source_type", "pdf"),
                        "source_id": entity.get("source_id", ""),
                        "source_title": entity.get("source_title", ""),
                        "modality": entity.get("modality", "text"),
                        "section_title": entity.get("section_title", ""),
                        "figure_id": entity.get("figure_id", ""),
                        "image_path": entity.get("image_path", ""),
                        "caption": entity.get("caption", ""),
                        "speaker": entity.get("speaker", ""),
                        "page_number": entity.get("page_number", 0),
                        "start_ts": entity.get("start_ts", 0),
                        "content_hash": entity.get("content_hash", ""),
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
        """Gemini text channel + Chinese-CLIP channel, merge by chunk_id."""
        text_hits = self.search(
            query,
            owner_uid=owner_uid,
            project_id=project_id,
            top_k=top_k,
            vector_field="text_vector",
        )
        image_hits = self.search(
            query,
            owner_uid=owner_uid,
            project_id=project_id,
            top_k=top_k,
            vector_field="image_vector",
        )

        merged: dict[str, dict] = {}
        for hit in text_hits + image_hits:
            cid = hit["chunk_id"]
            if cid not in merged or hit["score"] > merged[cid]["score"]:
                merged[cid] = hit
            else:
                merged[cid]["score"] = min(1.0, merged[cid]["score"] + 0.05)

        return sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:top_k]
