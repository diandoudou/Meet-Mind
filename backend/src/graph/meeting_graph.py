"""LangGraph pipeline for post-meeting parallel processing."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from agents.action_agent import action_node
from agents.summary_agent import summary_node
from graph.state import MeetingGraphState


def merge_results_node(state: MeetingGraphState) -> Dict[str, Any]:
    """Fan-in node after parallel summary/action branches."""
    return {}


@lru_cache(maxsize=1)
def _compile_graph():
    graph = StateGraph(MeetingGraphState)

    graph.add_node("summary", summary_node)
    graph.add_node("action", action_node)
    graph.add_node("merge_results", merge_results_node)

    graph.add_edge(START, "summary")
    graph.add_edge(START, "action")
    graph.add_edge("summary", "merge_results")
    graph.add_edge("action", "merge_results")
    graph.add_edge("merge_results", END)

    return graph.compile()


def get_post_meeting_graph():
    return _compile_graph()


async def run_post_meeting_pipeline(initial_state: MeetingGraphState) -> MeetingGraphState:
    graph = get_post_meeting_graph()
    return await graph.ainvoke(initial_state)
