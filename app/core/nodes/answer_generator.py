"""answer_generator — natural language answer from plan / parsed results."""

from __future__ import annotations

from typing import Any

from app.agents.answer import AnswerAgent
from app.core.state import ChatState


def answer_generator(state: ChatState) -> dict[str, Any]:
    agent = AnswerAgent()
    text = agent.render(dict(state))
    return {"answer": text or "Done."}
