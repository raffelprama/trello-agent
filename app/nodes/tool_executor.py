"""Deprecated: execution lives in specialist agents invoked by plan_executor."""

from __future__ import annotations

from typing import Any

from app.state import ChatState


def tool_executor(state: ChatState) -> dict[str, Any]:
    raise RuntimeError("tool_executor was removed in the A2A rewrite; use plan_executor + AgentBus.")


__all__ = ["tool_executor"]
