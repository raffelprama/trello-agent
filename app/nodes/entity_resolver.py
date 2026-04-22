"""Deprecated: entity resolution lives in specialist agents (Board/List/Card/...)."""

from __future__ import annotations

from typing import Any

from app.state import ChatState


def entity_resolver(state: ChatState) -> dict[str, Any]:
    raise RuntimeError(
        "entity_resolver was removed in the A2A rewrite; use OrchestratorAgent + specialist agents.",
    )


__all__ = ["entity_resolver"]
