"""Embedding function wrapper with local fallback."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List


def _hash_embedding_function():
    class HashEmbeddingFunction:
        """Deterministic bag-of-tokens embedding for offline/dev without heavy deps."""

        def __call__(self, input: List[str]) -> List[List[float]]:
            dim = 256
            out: List[List[float]] = []
            for text in input:
                vec = [0.0] * dim
                for token in (text or "").lower().split():
                    vec[hash(token) % dim] += 1.0
                norm = sum(v * v for v in vec) ** 0.5 or 1.0
                out.append([v / norm for v in vec])
            return out

        def name(self) -> str:
            return "hash-fallback"

    return HashEmbeddingFunction()


@lru_cache(maxsize=1)
def get_embedding_function():
    """Prefer Gemini embeddings; fall back to hash / Chroma default."""
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("RAG_EMBEDDING_MODEL", "gemini-embedding-001")

    if api_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings

            embeddings = GoogleGenerativeAIEmbeddings(
                model=model,
                google_api_key=api_key,
            )
            fallback = _hash_embedding_function()

            class LangChainEmbeddingFunction:
                def __init__(self) -> None:
                    self._ok = True

                def __call__(self, input: List[str]) -> List[List[float]]:
                    if not self._ok:
                        return fallback(input)
                    try:
                        return embeddings.embed_documents(input)
                    except Exception as exc:
                        print(f"[RAG] Gemini embed failed, switching to hash fallback: {exc}")
                        self._ok = False
                        return fallback(input)

                def name(self) -> str:
                    return "gemini" if self._ok else "hash-fallback"

            return LangChainEmbeddingFunction()
        except Exception as exc:
            print(f"[RAG] Gemini embedding unavailable, using local fallback: {exc}")

    try:
        from chromadb.utils import embedding_functions

        return embedding_functions.DefaultEmbeddingFunction()
    except Exception:
        pass

    print("[RAG] Using hash embedding fallback")
    return _hash_embedding_function()


def embed_texts(texts: List[str]) -> List[List[float]]:
    fn = get_embedding_function()
    return fn(texts)


def clear_embedding_cache() -> None:
    get_embedding_function.cache_clear()
