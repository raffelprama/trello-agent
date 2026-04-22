"""ReflectionAgent — graceful failure when plan execution or orchestration fails."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm import get_chat_model, invoke_chat_logged

logger = logging.getLogger(__name__)


class ReflectionAgent:
    name = "reflection"

    def render(self, state: dict[str, Any]) -> str:
        question = state.get("question", "")
        err = state.get("error_message") or ""
        eval_reason = (state.get("evaluation_result") or {}).get("reason") or ""
        trace = state.get("plan_trace") or []

        llm = get_chat_model(0)
        prompt = f"""The Trello assistant could not complete the request.
Explain briefly what went wrong and what the user could try next.

User question: {question}
Error: {err}
Evaluation: {eval_reason}
Plan trace (last steps): {json.dumps(trace[-6:], default=str)[:3000]}

If something was not found, suggest checking spelling or listing available boards/lists from a prior successful turn.
"""

        try:
            msg = invoke_chat_logged(
                llm,
                [
                    {"role": "system", "content": "Be concise and helpful."},
                    {"role": "user", "content": prompt},
                ],
                operation="reflection_agent",
            )
            text = getattr(msg, "content", str(msg))
            return text or "Sorry, something went wrong."
        except Exception as e:
            logger.exception("ReflectionAgent")
            return f"I couldn't complete that. ({e})"
