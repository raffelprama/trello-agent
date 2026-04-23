"""Heuristic disambiguation for Done list vs dueComplete — corrects LLM false positives on 'mark done'."""

from __future__ import annotations

import re
from typing import Any


def resolve_unambiguous_done_intent(user_text: str) -> str | None:
    """
    If the user text clearly picks one action, return CARD_SET_DUE_COMPLETE or CARD_MOVE.
    Otherwise None (keep analyzer / clarification).
    """
    t = re.sub(r"\s+", " ", (user_text or "").strip().lower())

    has_mark = bool(re.search(r"\bmark\b", t))
    has_done_word = bool(re.search(r"\bdone\b", t))
    has_complete = bool(re.search(r"\bcomplete\b", t))

    set_to_done = bool(
        re.search(r"\bset\b", t)
        and re.search(r"\bto\b", t)
        and has_done_word
        and "done list" not in t
        and "done column" not in t,
    )
    mark_complete = (
        (has_mark and (has_done_word or has_complete))
        or set_to_done
        or "due complete" in t
        or "duecomplete" in t
        or "checkmark" in t
    )
    move_done = (
        (bool(re.search(r"\bmove\b", t)) and has_done_word)
        or "done list" in t
        or "done column" in t
        or bool(re.search(r"\bput\b.*\bdone\b", t))
    )

    if mark_complete and move_done:
        return None
    if mark_complete:
        return "CARD_SET_DUE_COMPLETE"
    if move_done:
        return "CARD_MOVE"
    return None


def apply_done_intent_heuristic(analysis: Any, user_text: str) -> Any:
    """Clear mistaken needs_intent_clarification when wording is unambiguous."""
    if not getattr(analysis, "needs_intent_clarification", False):
        return analysis
    label = resolve_unambiguous_done_intent(user_text)
    if label is None:
        return analysis
    return analysis.model_copy(
        update={
            "needs_intent_clarification": False,
            "clarification_question": "",
            "suggested_final_intent": label,
        }
    )
