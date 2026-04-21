"""clarify — surface a clarification question and end the turn."""

from __future__ import annotations

import logging
from typing import Any

from app.state import ChatState

logger = logging.getLogger(__name__)


def clarify_node(state: ChatState) -> dict[str, Any]:
    q = (state.get("clarification_question") or "").strip() or "Could you clarify what you mean?"
    logger.info("[clarify] %s", q[:200])
    return {
        "answer": q,
        "parsed_response": {"clarification": True, "question": q},
        "http_status": 200,
        "error_message": "",
        "evaluation_result": {"status": "success", "reason": "clarification"},
        "evaluation_retry_count": int(state.get("evaluation_retry_count") or 0),
    }
