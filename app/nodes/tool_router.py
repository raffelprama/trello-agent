"""Deprecated: tool routing replaced by Plan + AgentBus."""

from __future__ import annotations

from typing import Any

from app.state import ChatState


def tool_router(state: ChatState) -> dict[str, Any]:
    raise RuntimeError("tool_router was removed in the A2A rewrite; use plan_executor + AgentBus.")


__all__ = ["tool_router"]
