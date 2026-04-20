"""reflection_node — graceful failure explanation."""

from __future__ import annotations

import logging
from typing import Any

from app.llm import get_chat_model
from app.state import ChatState

logger = logging.getLogger(__name__)


def reflection_node(state: ChatState) -> dict[str, Any]:
    question = state.get("question", "")
    reasoning = state.get("reasoning_trace") or ""
    err = state.get("error_message") or ""
    eval_reason = (state.get("evaluation_result") or {}).get("reason") or ""

    llm = get_chat_model(0)
    prompt = f"""The Trello assistant could not complete the request satisfactorily.
Explain briefly and politely what went wrong and what the user could try next (e.g. check board/list names).

User question: {question}
Planner reasoning: {reasoning}
Error: {err}
Evaluation: {eval_reason}
"""

    try:
        msg = llm.invoke(
            [
                {"role": "system", "content": "Be concise and helpful."},
                {"role": "user", "content": prompt},
            ]
        )
        text = getattr(msg, "content", str(msg))
        return {"answer": text or "Sorry, something went wrong."}
    except Exception as e:
        logger.exception("reflection_node")
        return {"answer": f"I couldn't complete that. ({e})"}
