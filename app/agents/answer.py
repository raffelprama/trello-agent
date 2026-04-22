"""AnswerAgent — natural language answer from plan / parsed results."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.llm import get_chat_model, invoke_chat_logged

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

        llm = get_chat_model(0)
        prompt = f"""Summarize the Trello result for the user's latest question.

CURRENT user question (answer this): {question}
Plan intent: {intent}

AUTHORITATIVE data for this turn only (JSON):
{blob}

Prior conversation (context only — do NOT invent boards/cards from it):
{history_text}

Rules:
- Ground every factual claim in the JSON. If cards/lists/boards are listed, reflect counts and names accurately.
- If the user asked to see all cards on a board, list or summarize cards from the "cards" array.
- If "card" is present, summarize description, labels, due dates, checklists, members.
- If clarification is true, the assistant is only asking a question — repeat it politely.
- Do not invent IDs.
- Format for readability: use short paragraphs and a blank line between sections when you cover several topics (e.g. board name, then lists, then cards). Avoid a single wall of text when there are many items."""

        try:
            msg = invoke_chat_logged(
                llm,
                [
                    {
                        "role": "system",
                        "content": (
                            "Be accurate and clear. Ground every factual claim in the AUTHORITATIVE "
                            "JSON only. Leave a little breathing room: short paragraphs and spacing "
                            "between sections when listing multiple boards, lists, or cards."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                operation="answer_agent",
            )
            text = getattr(msg, "content", str(msg))
            return text or "Done."
        except Exception as e:
            logger.exception("AnswerAgent")
            return f"Completed with data: {blob[:2000]}" if parsed else str(e)
