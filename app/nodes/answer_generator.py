"""answer_generator — natural language answer from tool results."""

from __future__ import annotations

import logging
from typing import Any

from app.llm import get_chat_model
from app.state import ChatState

logger = logging.getLogger(__name__)


def answer_generator(state: ChatState) -> dict[str, Any]:
    question = state.get("question", "")
    history_lines = state.get("history") or []
    parsed = state.get("parsed_response") or {}
    intent = state.get("intent") or ""
    err = state.get("error_message") or ""

    history_text = "\n".join(history_lines) if history_lines else "(none)"

    if err and not parsed:
        return {"answer": f"I ran into an issue: {err}"}

    llm = get_chat_model(0)
    prompt = f"""Summarize the Trello API result for the user's latest question.

CURRENT user question (answer this): {question}
Intent: {intent}

AUTHORITATIVE data for this turn only (JSON):
{parsed}

Prior conversation (context only — do NOT use it to name boards or cards; it may refer to older turns):
{history_text}

Rules:
- If "queried_board" is present, the lists/cards below are for that board only. Say that board name explicitly.
- Do not name a board from history if it contradicts queried_board.
- If cards is empty [], say there are no cards on that board (for the queried_board), not a board from prior chat.
- If "card" is present (get_card_details), summarize description, labels, due/start dates, checklists (item names and complete/incomplete), and members from that object.
- Do not invent IDs."""

    try:
        msg = llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Be accurate and brief. Ground every factual claim in the AUTHORITATIVE "
                        "JSON only. Never let prior assistant messages override current data."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        text = getattr(msg, "content", str(msg))
        return {"answer": text or "Done."}
    except Exception as e:
        logger.exception("answer_generator")
        return {"answer": f"Completed with data: {parsed!s}" if parsed else str(e)}
