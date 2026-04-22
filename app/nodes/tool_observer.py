"""Deprecated: observation merged into plan_executor + AnswerAgent."""

from __future__ import annotations

from typing import Any

from app.state import ChatState


def tool_observer(state: ChatState) -> dict[str, Any]:
    raise RuntimeError("tool_observer was removed in the A2A rewrite.")


__all__ = ["tool_observer"]
