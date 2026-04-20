"""normalize_intent_planner — LLM extracts intent + entities."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import BOARD_SCOPE_ONLY, DELETE_ITEM, TRELLO_BOARD_ID
from app.llm import get_chat_model
from app.state import ChatState

logger = logging.getLogger(__name__)

class PlannerOutput(BaseModel):
    intent: Literal[
        "get_boards",
        "get_lists",
        "get_cards",
        "get_board_cards",
        "get_card_details",
        "create_card",
        "update_card",
        "move_card",
        "delete_card",
    ]
    entities: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


SYSTEM = """You are a Trello intent planner. Given the user message and optional prior conversation lines,
output a single structured plan.

Intents (choose exactly one):
- get_boards: list all boards the user can access
- get_lists: lists on a board (needs board_name or implied default board)
- get_cards: cards in a single named list only (needs list_name and board context)
- get_board_cards: all cards across every list on a board — use when the user asks for every/all cards, whole board, or all lists (needs board_name or default board; do NOT use get_cards for that)
- get_card_details: full info for ONE card — description, due/start dates, labels, checklists, members. Use when the user asks to see/open/describe a card by name, or asks for labels, checklist, description, or due date of a card (needs card_name; board context optional)
- create_card: create a card (needs list_name, card_name; optional description)
- update_card: update card fields (needs card identification by name; optional description/due)
- move_card: move a card to another list (needs card_name, target list_name)
- delete_card: permanently delete a card (needs card_name; only if the user clearly wants removal/deletion)

Entities (use only relevant keys, all optional strings unless noted):
- board_name: human name of board
- list_name: source list for get_cards / create_card
- target_list_name: destination list for move_card
- card_name: title of card (for lookup)
- new_card_name: new title when updating a card
- description: card description text
- due: due date if mentioned (ISO or natural; we pass through)

Normalize names; do not invent IDs. If ambiguous, still pick best-effort intent and entities."""


def _planner_system() -> str:
    s = SYSTEM
    if BOARD_SCOPE_ONLY and TRELLO_BOARD_ID:
        s += (
            "\n\nIMPORTANT: This deployment is limited to ONE Trello board "
            f"(id={TRELLO_BOARD_ID}). Do not plan actions on other boards; "
            "omit board_name or use only that board's name."
        )
    return s


USER_TEMPLATE = """User question:
{question}

Prior conversation (oldest first, may be empty):
{history}
"""


def _maybe_coerce_board_cards(
    question: str,
    history_lines: list[str],
    intent: str,
    entities: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """get_cards requires list_name; if user wants all cards on the board, use get_board_cards."""
    if intent != "get_cards":
        return intent, entities
    if (entities.get("list_name") or "").strip():
        return intent, entities
    q = question.lower()
    combined = q + " " + " ".join(history_lines).lower()
    wants_all = (
        "every card" in q
        or "all cards" in q
        or "all card" in q
        or "all the cards" in q
        or "each list" in q
        or "all lists" in q
        or "whole board" in q
        or "entire board" in q
        or (" in there" in q and ("every" in q or "all" in q) and "card" in q)
        or ("every card" in combined and " in there" in combined)
    )
    if wants_all:
        return "get_board_cards", entities
    return intent, entities


def _maybe_coerce_card_details(
    question: str,
    intent: str,
    entities: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Single-card drill-down without a list → get_card_details, not get_cards."""
    e = dict(entities)
    if intent == "get_card_details":
        return intent, e
    q = question.lower()
    wants_details = any(
        x in q
        for x in (
            "label",
            "checklist",
            "description",
            "due date",
            "detail",
            "more about",
            "what's on",
            "whats on",
        )
    )
    has_card = bool((e.get("card_name") or "").strip())
    has_list = bool((e.get("list_name") or "").strip())
    if intent == "get_cards" and has_card and not has_list:
        return "get_card_details", e
    if intent == "get_cards" and wants_details and has_card:
        return "get_card_details", e
    return intent, e


def _enrich_card_details_entities(question: str, entities: dict[str, Any]) -> dict[str, Any]:
    """Extract card title from phrases like 'see Ai card' / 'show the Foo card'."""
    e = dict(entities)
    if (e.get("card_name") or "").strip():
        return e
    q = question.strip()
    m = re.search(
        r"(?:see|show|view|open|about)\s+(?:the\s+)?(.+?)\s+card\b",
        q,
        re.IGNORECASE,
    )
    if m:
        e["card_name"] = m.group(1).strip().strip('"').strip("'")
        return e
    m = re.search(
        r"card\s+(?:named|called)\s+[\"']?([^\"']+)[\"']?",
        q,
        re.IGNORECASE,
    )
    if m:
        e["card_name"] = m.group(1).strip()
    return e


def _enrich_create_card_entities(question: str, entities: dict[str, Any]) -> dict[str, Any]:
    """Fill list_name / card_name from wording when the model omits them."""
    e = dict(entities)
    q = question.strip()
    if not (e.get("list_name") or "").strip():
        m = re.search(
            r"\bin\s+(.+?)\s+with\s+(?:the\s+)?name",
            q,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            e["list_name"] = m.group(1).strip().strip('"').strip("'")
    if not (e.get("card_name") or "").strip():
        m = re.search(r'name\s+of\s+["\']([^"\']+)["\']', q, re.IGNORECASE)
        if m:
            e["card_name"] = m.group(1).strip()
        else:
            m = re.search(r"name\s+of\s+(\S+)", q, re.IGNORECASE)
            if m:
                e["card_name"] = m.group(1).strip().strip('"').strip("'")
    return e


def normalize_intent_planner(state: ChatState) -> dict[str, Any]:
    question = state.get("question", "").strip()
    history_lines = state.get("history") or []
    history_text = "\n".join(history_lines) if history_lines else "(none)"

    llm = get_chat_model(0).with_structured_output(
        PlannerOutput,
        method="function_calling",
    )
    prompt = USER_TEMPLATE.format(question=question, history=history_text)
    try:
        out: PlannerOutput = llm.invoke(
            [
                {"role": "system", "content": _planner_system()},
                {"role": "user", "content": prompt},
            ]
        )
    except Exception as e:
        logger.exception("Planner failed")
        return {
            "intent": "planner_error",
            "entities": {},
            "reasoning_trace": f"Planner error: {e}",
            "cleaned_query": question,
            "error_message": str(e),
            "skip_tools": True,
        }

    intent, entities = _maybe_coerce_board_cards(
        question, history_lines, out.intent, dict(out.entities)
    )
    intent, entities = _maybe_coerce_card_details(question, intent, entities)

    if intent == "create_card":
        entities = _enrich_create_card_entities(question, entities)
    if intent == "get_card_details":
        entities = _enrich_card_details_entities(question, entities)

    if intent == "delete_card" and not DELETE_ITEM:
        return {
            "intent": "delete_card",
            "entities": entities,
            "reasoning_trace": out.reasoning,
            "cleaned_query": question,
            "error_message": (
                "Deleting or removing cards is disabled (DELETE_ITEM=false). "
                "Set DELETE_ITEM=true in .env to enable delete_card."
            ),
            "skip_tools": True,
        }

    return {
        "intent": intent,
        "entities": entities,
        "reasoning_trace": out.reasoning,
        "cleaned_query": question,
        "error_message": "",
        "skip_tools": False,
    }
