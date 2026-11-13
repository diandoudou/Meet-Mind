"""LangGraph shared state for post-meeting processing."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, TypedDict


class MeetingGraphState(TypedDict, total=False):
    meeting_id: str
    project_id: str
    transcript_text: str

    summary_structured: Dict[str, Any]
    summary_text: str
    action_items: List[Dict[str, Any]]

    errors: Annotated[List[str], operator.add]
