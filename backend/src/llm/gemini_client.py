"""Shared Gemini LLM client for backend agents."""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI


@lru_cache(maxsize=4)
def get_gemini_llm(temperature: float = 0.3) -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GEMINI_API_KEY", "").strip().strip('"')
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured in backend/.env")

    model = os.getenv("GEMINI_MODEL_NAME", "gemini-3.6-flash").strip().strip('"')
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )


def clear_gemini_llm_cache() -> None:
    get_gemini_llm.cache_clear()
