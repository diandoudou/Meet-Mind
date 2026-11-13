"""RAG chat with citation-constrained generation (papers + meetings)."""

from __future__ import annotations

import re
import time
from typing import List, Optional

from langchain_core.prompts import ChatPromptTemplate

from llm.gemini_client import get_gemini_llm
from rag.models import RagChatResponse, RagCitation, SearchResult
from rag.retriever import search_knowledge


RAG_SYSTEM_PROMPT = """你是 MeetMind 企业知识助手。
只能根据「检索上下文」回答，禁止编造未出现在上下文中的事实。
每条关键事实必须在句末标注引用编号，如 [1] 或 [1][2]。
若引用论文图表，可使用上下文中的标签（如 [1:Fig.2]）。
若上下文不足以回答，请明确说明「知识库中未找到相关信息」。"""

RAG_USER_PROMPT = """## 检索上下文
{context}

## 用户问题
{question}

请基于上下文回答，并保留引用编号。"""


def _build_context(results: List[SearchResult]) -> str:
    lines: List[str] = []
    for item in results:
        meta_parts = [item.source_type, item.source_title, f"modality={item.modality}"]
        if item.section_title:
            meta_parts.append(f"section={item.section_title}")
        if item.page_number:
            meta_parts.append(f"page={item.page_number}")
        if item.figure_id:
            meta_parts.append(f"figure={item.figure_id}")
        if item.speaker:
            meta_parts.append(f"speaker={item.speaker}")
        body = item.text
        if item.caption and item.modality == "image":
            body = f"{body}\n(caption: {item.caption})"
        lines.append(f"{item.citation_label} ({', '.join(meta_parts)})\n{body}")
    return "\n\n".join(lines)


def _extract_citations(answer: str, results: List[SearchResult]) -> List[RagCitation]:
    # Match [1], [1:p3], [2:Fig.1]
    labels = set(re.findall(r"\[(\d+(?::[^\]]+)?)\]", answer))
    citations: List[RagCitation] = []
    lookup = {r.citation_label.strip("[]"): r for r in results}
    # also allow bare numeric labels → first matching index
    by_index = {str(i): r for i, r in enumerate(results, start=1)}

    for label in sorted(labels, key=lambda x: int(re.match(r"(\d+)", x).group(1)) if re.match(r"(\d+)", x) else 0):
        result = lookup.get(label) or by_index.get(label.split(":")[0])
        if not result:
            continue

        url_path = ""
        paper_types = {"pdf", "paper_section", "paper_table", "paper_figure"}
        if result.source_type in ("meeting_transcript", "meeting_summary"):
            url_path = f"/project/{result.project_id}?meeting={result.source_id}"
        elif result.source_type in paper_types:
            url_path = f"/project/{result.project_id}?file={result.source_id}"
            if result.page_number:
                url_path += f"&page={result.page_number}"
            if result.figure_id:
                url_path += f"&figure={result.figure_id}"

        excerpt = result.text[:240] + ("..." if len(result.text) > 240 else "")
        citations.append(
            RagCitation(
                label=f"[{label}]",
                chunk_id=result.chunk_id,
                source_type=result.source_type,
                source_id=result.source_id,
                source_title=result.source_title,
                excerpt=excerpt,
                url_path=url_path,
                page_number=result.page_number,
                figure_id=result.figure_id,
                image_path=result.image_path,
                modality=result.modality,
            )
        )
    return citations


def _fallback_answer(results: List[SearchResult]) -> str:
    if not results:
        return "知识库中未找到相关信息。请先完成会议录制或上传 PDF 文档以建立索引。"
    lines = ["根据检索到的文献片段："]
    for item in results[:3]:
        excerpt = item.text.strip().replace("\n", " ")
        if len(excerpt) > 280:
            excerpt = excerpt[:280] + "..."
        lines.append(f"{item.citation_label} {excerpt}")
    return "\n".join(lines)


def _response_text(response) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                text = getattr(block, "text", None)
                parts.append(str(text if text is not None else block))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def rag_chat(
    message: str,
    *,
    owner_uid: str,
    project_id: str = "",
    project_name: str = "",
    top_k: int = 6,
) -> RagChatResponse:
    started = time.time()
    results = search_knowledge(
        message,
        owner_uid=owner_uid,
        project_id=project_id or None,
        project_name=project_name,
        top_k=top_k,
    )

    if not results:
        return RagChatResponse(
            answer="知识库中未找到相关信息。请先完成会议录制或上传 PDF 文档以建立索引。",
            citations=[],
            retrieval_meta={"chunks_used": 0, "latency_ms": int((time.time() - started) * 1000)},
        )

    context = _build_context(results)

    try:
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", RAG_SYSTEM_PROMPT),
                ("human", RAG_USER_PROMPT),
            ]
        )
        chain = prompt | get_gemini_llm(temperature=0.2)
        response = chain.invoke({"context": context, "question": message})
        answer = _response_text(response)
    except Exception as exc:
        print(f"[RAG] chat generation failed: {exc}")
        answer = _fallback_answer(results)

    citations = _extract_citations(answer, results)
    return RagChatResponse(
        answer=answer,
        citations=citations,
        retrieval_meta={
            "chunks_used": len(results),
            "latency_ms": int((time.time() - started) * 1000),
            "modalities": sorted({r.modality for r in results}),
        },
    )
