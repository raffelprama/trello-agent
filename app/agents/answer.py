"""AnswerAgent — natural language answer from plan / parsed results."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.llm import get_chat_model, invoke_chat_logged
from app.prompt.answer import ANSWER_SYSTEM, format_answer_user
from app.utils.time_context import format_reference_time_for_prompt

logger = logging.getLogger(__name__)


class AnswerAgent:
    """Renders the final user-facing answer from authoritative JSON."""

    name = "answer"

    def render(self, state: dict[str, Any]) -> str:
        question = state.get("question", "")
        history_lines = state.get("history") or []
        parsed = state.get("parsed_response") or {}
        intent = state.get("intent") or ""

        history_text = "\n".join(history_lines) if history_lines else "(none)"
        blob = json.dumps(parsed, ensure_ascii=False, default=str) if parsed else "{}"
        mem = state.get("memory")
        reference_time_block = format_reference_time_for_prompt(mem if isinstance(mem, dict) else None)

        llm = get_chat_model(0)
        prompt = format_answer_user(
            question=question,
            intent=intent,
            blob=blob,
            history_text=history_text,
            reference_time_block=reference_time_block,
        )

        try:
            msg = invoke_chat_logged(
                llm,
                [
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                operation="answer_agent",
            )
            text = getattr(msg, "content", str(msg))
            return text or "Done."
        except Exception as e:
            logger.exception("AnswerAgent")
            return f"Completed with data: {blob[:2000]}" if parsed else str(e)
