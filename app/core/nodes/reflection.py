"""reflection_node — graceful failure (ReflectionAgent)."""

from __future__ import annotations

from typing import Any

from app.agents.reflection import ReflectionAgent
from app.core.state import ChatState


def reflection_node(state: ChatState) -> dict[str, Any]:
    agent = ReflectionAgent()
    text = agent.render(dict(state))
    return {"answer": text or "Sorry, something went wrong."}
