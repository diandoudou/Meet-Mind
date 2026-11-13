"""Backend chat API powered by Gemini (server-side only)."""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from llm.gemini_client import get_gemini_llm

SYSTEM_INSTRUCTION = """You are MeetMind, an AI meeting and project assistant.
Answer based on the provided project context. Be concise, accurate, and helpful.
If the context does not contain enough information, say so clearly."""


def generate_chat_reply(message: str, context: str = "") -> str:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_INSTRUCTION + "\n\nContext:\n{context}"),
            ("human", "{message}"),
        ]
    )
    chain = prompt | get_gemini_llm(temperature=0.4)
    result = chain.invoke({"context": context or "No context provided.", "message": message})
    return getattr(result, "content", str(result))
