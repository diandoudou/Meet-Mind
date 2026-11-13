"""Pydantic schemas for structured meeting outputs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TopicSummary(BaseModel):
    title: str
    discussion_points: List[str] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)
    conclusion: str = ""


class MeetingSummaryStructured(BaseModel):
    title: str = "Meeting Summary"
    date: str = ""
    participants: List[str] = Field(default_factory=list)
    topics: List[TopicSummary] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)
    overview: str = ""


class ActionItemExtracted(BaseModel):
    assignee: str = "未指定"
    task: str
    deadline: str = ""
    priority: str = "medium"
    context: str = ""


class ActionItemsResult(BaseModel):
    action_items: List[ActionItemExtracted] = Field(default_factory=list)


def format_summary_text(summary: MeetingSummaryStructured) -> str:
    """Render structured summary as readable markdown-like text."""
    lines = [f"# {summary.title}", ""]

    if summary.overview:
        lines.extend(["## 会议概要", summary.overview, ""])

    if summary.participants:
        lines.extend(["## 参会人", ", ".join(summary.participants), ""])

    for index, topic in enumerate(summary.topics, start=1):
        lines.append(f"## 议题 {index}: {topic.title}")
        for point in topic.discussion_points:
            lines.append(f"- {point}")
        if topic.conclusion:
            lines.append(f"- **结论**: {topic.conclusion}")
        lines.append("")

    if summary.decisions:
        lines.extend(["## 会议决策", *[f"- {item}" for item in summary.decisions], ""])

    if summary.next_steps:
        lines.extend(["## 下一步计划", *[f"- {item}" for item in summary.next_steps], ""])

    return "\n".join(line for line in lines if line is not None).strip()
