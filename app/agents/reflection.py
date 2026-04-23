"""ReflectionAgent — graceful failure when plan execution or orchestration fails."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.llm import get_chat_model, invoke_chat_logged
from app.prompt.reflection import REFLECTION_SYSTEM, format_reflection_user

logger = logging.getLogger(__name__)


class ReflectionAgent:
    name = "reflection"

    def render(self, state: dict[str, Any]) -> str:
        question = state.get("question", "")
        err = state.get("error_message") or ""
        eval_reason = (state.get("evaluation_result") or {}).get("reason") or ""
        trace = state.get("plan_trace") or []

        llm = get_chat_model(0)
        trace_snippet = json.dumps(trace[-6:], default=str)[:3000]
        prompt = format_reflection_user(
            question=question,
            err=err,
            eval_reason=eval_reason,
            trace_snippet=trace_snippet,
        )

        try:
            msg = invoke_chat_logged(
                llm,
                [
                    {"role": "system", "content": REFLECTION_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                operation="reflection_agent",
            )
            text = getattr(msg, "content", str(msg))
            return text or "Sorry, something went wrong."
        except Exception as e:
            logger.exception("ReflectionAgent")
            return f"I couldn't complete that. ({e})"
