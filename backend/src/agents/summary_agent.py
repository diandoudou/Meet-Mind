"""Structured meeting summary agent powered by LangChain."""

from __future__ import annotations

from typing import Any, Dict

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from llm.gemini_client import get_gemini_llm
from models.schemas import MeetingSummaryStructured, format_summary_text


SUMMARY_SYSTEM_PROMPT = """你是一位专业的会议纪要助手。
请根据会议转写文本生成结构化纪要，使用中文输出。
必须严格返回 JSON，不要添加任何额外说明。"""

SUMMARY_USER_PROMPT = """请根据以下会议转写文本生成结构化会议纪要。

## 会议转写文本
{transcript}

## 输出 JSON 字段
- title: 会议主题
- date: 会议日期（无法确定则留空）
- participants: 参会人列表
- topics: 议题数组，每项包含 title, discussion_points, participants, conclusion
- decisions: 决策列表
- next_steps: 下一步计划
- overview: 2-3 句会议概要

{format_instructions}"""


class SummaryAgent:
    def __init__(self) -> None:
        self.parser = JsonOutputParser(pydantic_object=MeetingSummaryStructured)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SUMMARY_SYSTEM_PROMPT),
                ("human", SUMMARY_USER_PROMPT),
            ]
        )
        self.chain = self.prompt | get_gemini_llm(temperature=0.3) | self.parser

    def generate(self, transcript_text: str) -> MeetingSummaryStructured:
        if not transcript_text.strip():
            return MeetingSummaryStructured(
                title="空会议",
                overview="暂无会议内容，无法生成总结。",
            )

        return self.chain.invoke(
            {
                "transcript": transcript_text,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )

    @staticmethod
    def fallback(transcript_text: str, error: str) -> MeetingSummaryStructured:
        speakers = set()
        for line in transcript_text.splitlines():
            if ":" in line:
                speakers.add(line.split(":", 1)[0].strip())

        return MeetingSummaryStructured(
            title="会议纪要（降级模式）",
            participants=sorted(speakers),
            topics=[],
            decisions=[],
            next_steps=[],
            overview=f"LLM 摘要失败，已降级。原因: {error}",
        )


def summary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    transcript_text = state.get("transcript_text", "")
    agent = SummaryAgent()

    try:
        structured = agent.generate(transcript_text)
        if isinstance(structured, dict):
            structured = MeetingSummaryStructured.model_validate(structured)

        summary_text = format_summary_text(structured)
        return {
            "summary_structured": structured.model_dump(),
            "summary_text": summary_text,
        }
    except Exception as exc:
        fallback = SummaryAgent.fallback(transcript_text, str(exc))
        return {
            "summary_structured": fallback.model_dump(),
            "summary_text": format_summary_text(fallback),
            "errors": [f"SummaryAgent: {exc}"],
        }
