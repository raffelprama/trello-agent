"""clarify — surface a clarification question, persist pending plan, end the turn."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.clarification import merge_pending_plan
from app.core.state import ChatState

logger = logging.getLogger(__name__)


def clarify_node(state: ChatState) -> dict[str, Any]:
    q = (state.get("clarification_question") or "").strip() or "Could you clarify what you mean?"
    logger.info("[clarify] %s", q[:200])
    mem = state.get("memory") or {}
    payload = state.get("pending_plan_payload")
    merged = merge_pending_plan(mem, payload if isinstance(payload, dict) else None)
    return {
        "answer": q,
        "parsed_response": {"clarification": True, "question": q},
        "http_status": 200,
        "error_message": "",
        "memory": merged,
        "evaluation_result": {"status": "success", "reason": "clarification"},
        "evaluation_retry_count": int(state.get("evaluation_retry_count") or 0),
    }
