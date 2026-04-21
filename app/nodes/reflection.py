"""reflection_node — graceful failure explanation."""

from __future__ import annotations

import logging
from typing import Any

from app.llm import get_chat_model, invoke_chat_logged
from app.state import ChatState

logger = logging.getLogger(__name__)


def reflection_node(state: ChatState) -> dict[str, Any]:
    question = state.get("question", "")
    reasoning = state.get("reasoning_trace") or ""
    err = state.get("error_message") or ""
    eval_reason = (state.get("evaluation_result") or {}).get("reason") or ""
    entities = state.get("entities") or {}

    llm = get_chat_model(0)
    prompt = f"""The Trello assistant could not complete the request satisfactorily.
Explain briefly and politely what went wrong and what the user could try next.

User question: {question}
Planner reasoning: {reasoning}
Error: {err}
Evaluation: {eval_reason}
Resolved entities (for context): board_id={entities.get('board_id')}, card_name={entities.get('card_name')}, list_name={entities.get('list_name')}, target_list_name={entities.get('target_list_name')}

If the error is about a card or list not being found, suggest the user check the exact spelling or list the available options from context.
If the card_name or target_list_name entity shows the user's intent, acknowledge it and guide them.
"""

    try:
        msg = invoke_chat_logged(
            llm,
            [
                {"role": "system", "content": "Be concise and helpful."},
                {"role": "user", "content": prompt},
            ],
            operation="reflection",
        )
        text = getattr(msg, "content", str(msg))
        return {"answer": text or "Sorry, something went wrong."}
    except Exception as e:
        logger.exception("reflection_node")
        return {"answer": f"I couldn't complete that. ({e})"}
