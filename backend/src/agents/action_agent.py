"""Action item extraction agent powered by LangChain."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from llm.gemini_client import get_gemini_llm
from models.schemas import ActionItemExtracted, ActionItemsResult


ACTION_SYSTEM_PROMPT = """你是一位专业的任务提取助手。
请从会议转写文本中提取明确的行动项/待办事项，使用中文。
只提取明确分配的任务，不要凭空创造。
必须严格返回 JSON。"""

ACTION_USER_PROMPT = """今天的日期是: {today}

## 会议转写文本
{transcript}

## 输出 JSON 字段
action_items: 数组，每项包含:
- assignee: 负责人
- task: 任务描述
- deadline: YYYY-MM-DD，没有则留空
- priority: low/medium/high/urgent
- context: 任务背景

{format_instructions}"""


class ActionAgent:
    def __init__(self) -> None:
        self.parser = JsonOutputParser(pydantic_object=ActionItemsResult)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ACTION_SYSTEM_PROMPT),
                ("human", ACTION_USER_PROMPT),
            ]
        )
        self.chain = self.prompt | get_gemini_llm(temperature=0.2) | self.parser

    def extract(self, transcript_text: str) -> List[ActionItemExtracted]:
        if not transcript_text.strip():
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        result = self.chain.invoke(
            {
                "today": today,
                "transcript": transcript_text,
                "format_instructions": self.parser.get_format_instructions(),
            }
        )

        if isinstance(result, dict):
            parsed = ActionItemsResult.model_validate(result)
        else:
            parsed = result

        return parsed.action_items


def _deadline_to_ms(deadline: str) -> int:
    if not deadline:
        return int((datetime.now() + timedelta(days=7)).timestamp() * 1000)

    try:
        return int(datetime.strptime(deadline, "%Y-%m-%d").timestamp() * 1000)
    except ValueError:
        return int((datetime.now() + timedelta(days=7)).timestamp() * 1000)


def serialize_action_items(
    items: List[ActionItemExtracted],
    project_id: str = "",
    meeting_id: str = "",
) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        serialized.append(
            {
                "id": f"ai-{meeting_id or 'meeting'}-{index}",
                "projectId": project_id,
                "meetingId": meeting_id,
                "task": item.task,
                "assignee": item.assignee,
                "deadline": _deadline_to_ms(item.deadline),
                "priority": item.priority,
                "context": item.context,
                "status": "pending",
            }
        )
    return serialized


def action_node(state: Dict[str, Any]) -> Dict[str, Any]:
    transcript_text = state.get("transcript_text", "")
    project_id = state.get("project_id", "")
    meeting_id = state.get("meeting_id", "")
    agent = ActionAgent()

    try:
        extracted = agent.extract(transcript_text)
        action_items = serialize_action_items(extracted, project_id, meeting_id)
        return {"action_items": action_items}
    except Exception as exc:
        return {
            "action_items": [],
            "errors": [f"ActionAgent: {exc}"],
        }
