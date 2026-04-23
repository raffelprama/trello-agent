"""RouterNode — classifies task type (simple vs bulk) before routing to the right orchestrator."""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.core.llm import get_chat_model, invoke_chat_logged
from app.core.state import ChatState

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """Classify a Trello assistant request. Return JSON only.

task_type values:
- "simple": any single action, query, or sequential operations on one or a few entities
- "bulk": the SAME action must be applied to MULTIPLE items at once
  (e.g. "mark ALL cards as done", "archive all cards in a list", "move every card", "complete all tasks in list X")

Return: {"task_type": "simple" | "bulk", "reasoning": "one sentence", "collection": null | "cards" | "lists", "action": null | "short verb phrase"}"""


class _RouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: Literal["simple", "bulk"]
    reasoning: str = ""
    collection: str | None = None
    action: str | None = None


def router_node(state: ChatState) -> dict[str, Any]:
    mem: dict[str, Any] = state.get("memory") or {}
    pending = mem.get("pending_plan")

    # Pure state routing — resume and destructive-confirm paths need no LLM
    if isinstance(pending, dict) and pending.get("awaiting_destructive_confirm"):
        return {"task_type": "simple"}
    if isinstance(pending, dict) and pending.get("plan"):
        return {"task_type": "simple"}

    q = (state.get("question") or "").strip()
    if not q:
        return {"task_type": "simple"}

    try:
        llm = get_chat_model(0).with_structured_output(_RouteDecision)
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": ROUTER_SYSTEM}, {"role": "user", "content": q}],
            operation="router_classify",
        )
        decision = raw if isinstance(raw, _RouteDecision) else _RouteDecision.model_validate(raw)
        logger.info(
            "[router] task_type=%s collection=%s action=%s | %s",
            decision.task_type,
            decision.collection,
            decision.action,
            (decision.reasoning or "")[:80],
        )
        return {"task_type": decision.task_type}
    except Exception:
        logger.warning("[router] classify failed, defaulting to simple", exc_info=True)
        return {"task_type": "simple"}
