"""normalize_intent_planner — LLM extracts intent + entities (PRD v2)."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app.config import BOARD_SCOPE_ONLY, DELETE_ITEM, TRELLO_BOARD_ID
from app.llm import get_chat_model, invoke_chat_logged
from app.session_memory import memory_summary_for_planner
from app.state import ChatState

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = frozenset(
    {
        "get_member_me",
        "get_boards",
        "get_board",
        "update_board",
        "create_board",
        "get_lists",
        "create_list",
        "update_list",
        "archive_list",
        "get_cards",
        "get_board_cards",
        "get_card_details",
        "create_card",
        "update_card",
        "move_card",
        "delete_card",
        "get_card_checklists",
        "create_checklist",
        "delete_checklist",
        "get_checkitems",
        "create_checkitem",
        "check_item",
        "uncheck_item",
        "delete_checkitem",
        "get_comments",
        "create_comment",
        "update_comment",
        "delete_comment",
        "get_board_labels",
        "create_label",
        "add_card_label",
        "remove_card_label",
        "get_board_members",
        "get_board_actions",
    }
)


class PlannerOutput(BaseModel):
    intent: str = Field(description="One of the v2 intent names")
    entities: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    needs_clarification: bool = False
    clarification_question: str | None = None


SYSTEM = """You are a Trello intent planner. Given the user message, optional prior conversation, and SESSION MEMORY
(known board, lists, and recently shown cards), output a single structured plan.

LANGUAGE: The user may write in ANY language (English, Indonesian, Spanish, etc.). Extract intent and entities correctly regardless of language.
- Indonesian examples: "saya ingin melihat" = "I want to see", "kartu" = "card", "daftar" = "list", "pindahkan" = "move", "buat" = "create", "hapus" = "delete", "tambah" = "add"
- If the message contains a 24-character hex string (e.g. 69e5f5c6a9fbd49f7b9d0db3), that IS a Trello card ID — set it as card_id in entities and still extract the card_name from context.


Intents (choose exactly one valid intent name):
- get_member_me: authenticated user profile
- get_boards: list all boards
- get_board: board details (needs board_name or default from memory)
- update_board: rename/desc board (needs board_name; new_name or description in entities)
- create_board: new board (new_board_name)
- get_lists: lists on a board
- create_list: new list on board (list_name)
- update_list: rename/reposition list
- archive_list: archive a list
- get_cards: cards in ONE list/column (needs list_name)
- get_board_cards: ALL cards on the board (every list) — use for "all cards", "every card", "whole board"
- get_card_details: ONE card — description, labels, checklists, due, members. Use when user names a CARD or says "under X" where X is a card title from memory, or "details/open/show card X"
- create_card: new card (list_name, card_name; optional description, due)
- update_card: edit card (card_name; optional description, due, new_card_name)
- move_card: move card (card_name, target_list_name)
- delete_card: delete card by name (only if user clearly wants delete)
- get_card_checklists: checklists on a card (card_name)
- create_checklist: add checklist to card (card_name, checklist_name)
- delete_checklist: remove checklist (checklist_name; card_name)
- get_checkitems: items in a checklist (checklist_name; card_name)
- create_checkitem: add item (checklist_name, card_name, check_item_name)
- check_item / uncheck_item: set checklist item state (card_name, checklist_name, check_item_name)
- delete_checkitem: remove item (card_name, checklist_name, check_item_name)
- get_comments: comments on card (card_name)
- create_comment: post comment (card_name, comment_text)
- update_comment: edit comment (action_id, comment_text)
- delete_comment: delete comment (action_id)
- get_board_labels: all labels on board
- create_label: new label on board (label_name; optional color)
- add_card_label / remove_card_label: (card_name, label_name)
- get_board_members: members on board
- get_board_actions: activity on board

Entities (use only relevant keys; strings unless noted):
- board_name, list_name, card_name, target_list_name, new_card_name, new_board_name
- checklist_name, check_item_name, label_name, comment_text
- description, due, color
- action_id (for comment update/delete)
- new_board_name / board_desc for create_board

CRITICAL — use SESSION MEMORY:
- If the user refers to a name that appears as a CARD in last_cards (e.g. "Ai", "under Ai", "see Ai", "Ai card"), prefer get_card_details with card_name set to that EXACT title from last_cards — NOT get_cards with list_name.
- "Under X" / "inside X" / "see X" / "show X": if X matches a list name in memory → get_cards; if X matches a card name in last_cards → get_card_details. Strip "the" prefix from X before matching.
- Pronouns ("that card", "it", "the first one"): use last_card_id / last_cards from memory; set card_name or ask for clarification.
- move_card: target_list_name MUST be an actual list name from memory. If the user says "move X to List" or "move X to a list" without naming a real list, set needs_clarification=true and ask which list.
- When a card name in the user message is short (1-3 chars) and appears in last_cards, always use that exact card name — do not expand or guess.

CLARIFICATION RESPONSE HANDLING (applies when memory shows pending_clarification):
- The user is answering your previous question — keep the SAME intent, do NOT switch to a different one.
- "Ai2", "the Ai2 card", "card name is Ai2", "Ai2 in On Going", "Ai2 card under On Going list" → set card_name="Ai2".
- For "multiple_cards" pending: set card_name to whatever the user specified; include list_name if they mentioned a list.
- For "card_name_missing" pending: the user's entire reply is almost certainly the card name — set card_name accordingly.
- NEVER reply with needs_clarification=true again for the same missing entity you just asked about.

If you cannot choose a single intent without guessing, set needs_clarification=true and a short clarification_question.

Normalize names; do not invent IDs."""


def _planner_system() -> str:
    s = SYSTEM
    if BOARD_SCOPE_ONLY and TRELLO_BOARD_ID:
        s += (
            "\n\nIMPORTANT: This deployment is limited to ONE Trello board "
            f"(id={TRELLO_BOARD_ID}). Omit board_name or use only that board."
        )
    return s


USER_TEMPLATE = """User question:
{question}

Prior conversation (oldest first, may be empty):
{history}

SESSION MEMORY (authoritative for recent cards/lists on this board):
{memory}
"""


def _coerce_intent(intent: str) -> str:
    if intent in ALLOWED_INTENTS:
        return intent
    logger.warning("Unknown intent from planner: %s", intent)
    return "get_boards"


def _maybe_coerce_board_cards(
    question: str,
    history_lines: list[str],
    intent: str,
    entities: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
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
    memory: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
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

    # Memory: explicit card title match for "under X" / "see X"
    ref = (e.get("list_name") or e.get("card_name") or "").strip()
    if not ref:
        m = re.search(r"(?:under|inside|see|show|view|about)\s+['\"]?([^'\"]+?)['\"]?\s*$", question.strip(), re.IGNORECASE)
        if m:
            ref = m.group(1).strip()
            # Strip leading navigation words so "under the Ai" → "Ai"
            ref = re.sub(r"^(?:under|inside)\s+(?:the\s+)?", "", ref, flags=re.IGNORECASE).strip()
            ref = re.sub(r"^the\s+", "", ref, flags=re.IGNORECASE).strip()
    last_cards = (memory or {}).get("last_cards") if memory else None
    if isinstance(last_cards, list) and ref and isinstance(memory, dict):
        hit = _fuzzy_card_name_from_memory(ref, memory)
        if hit:
            e["card_name"] = hit
            e.pop("list_name", None)
            return "get_card_details", e

    if intent == "get_cards" and has_card and not has_list:
        return "get_card_details", e
    if intent == "get_cards" and wants_details and has_card:
        return "get_card_details", e
    return intent, e


def _strip_card_noise(name: str) -> str:
    """Remove leading 'the card', 'card', extra whitespace."""
    s = (name or "").strip().strip('"').strip("'")
    s = re.sub(r"^(?:the\s+)?card\s+", "", s, flags=re.IGNORECASE).strip()
    return s


def _extract_card_name_fragment(question: str) -> str | None:
    """Pull a card title from common phrasings ('under card X', typos like infromation)."""
    q = question.strip()
    patterns = (
        # Clarification-response phrasings: "card name is X", "name is X", "it's called X"
        r"(?:card\s+(?:name\s+)?is|name\s+is|it['\s]+(?:called|named?))\s+[\"']?([^\"']+?)[\"']?\s*$",
        # "Ai2 card" at start of string (disambiguation response)
        r"^[\"']?([A-Za-z0-9][^\"']*?)[\"']?\s+card\b",
        r"(?:information|info|detail|infromation|inforation)\s+(?:under|about|on|for)\s+(?:the\s+)?(?:card\s+)?(.+?)(?:[.!?]|$)",
        r"(?:show|see|view|open|get)\s+(?:me\s+)?(?:the\s+)?(?:information|info|details?)\s+(?:under|about|on|for)\s+(?:the\s+)?(?:card\s+)?(.+?)(?:[.!?]|$)",
        r"(?:see|show|view|open)\s+(?:under|inside)\s+(?:the\s+)?(.+?)(?:[.!?]|$)",
        r"(?:under|about|on|for)\s+(?:the\s+)?card\s+(.+?)(?:[.!?]|$)",
        r"(?:see|show|view|open|about)\s+(?:the\s+)?(.+?)\s+card\b",
        r"card\s+(?:named|called)\s+[\"']?([^\"']+)[\"']?",
    )
    for pat in patterns:
        m = re.search(pat, q, re.IGNORECASE | re.DOTALL)
        if m:
            frag = _strip_card_noise(m.group(1))
            if frag:
                return frag
    return None


def _fuzzy_card_name_from_memory(ref: str, memory: dict[str, Any] | None) -> str | None:
    """If ref matches exactly one card name in last_cards (exact or substring), return canonical name."""
    if not memory or not ref.strip():
        return None
    lc = memory.get("last_cards")
    if not isinstance(lc, list):
        return None
    ref_n = ref.strip().lower()
    hits: list[str] = []
    for c in lc:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        nn = name.lower()
        if nn == ref_n or ref_n in nn or nn in ref_n:
            hits.append(name)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # Prefer shortest title (e.g. "test" → "Test 1" over "TEST_AGAIN")
        hits.sort(key=len)
        return hits[0]
    return None


def _enrich_card_details_entities(question: str, entities: dict[str, Any]) -> dict[str, Any]:
    e = dict(entities)
    q = question.strip()
    extracted = _extract_card_name_fragment(q)
    if extracted:
        e["card_name"] = extracted
        return e
    if (e.get("card_name") or "").strip():
        e["card_name"] = _strip_card_noise(str(e["card_name"]))
        return e
    m = re.search(
        r"(?:see|show|view|open|about)\s+(?:the\s+)?(.+?)\s+card\b",
        q,
        re.IGNORECASE,
    )
    if m:
        e["card_name"] = _strip_card_noise(m.group(1))
        return e
    m = re.search(
        r"card\s+(?:named|called)\s+[\"']?([^\"']+)[\"']?",
        q,
        re.IGNORECASE,
    )
    if m:
        e["card_name"] = _strip_card_noise(m.group(1))
    return e


def _refine_card_details_entities(
    question: str,
    entities: dict[str, Any],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    """After LLM: regex + memory fuzzy for get_card_details."""
    e = dict(entities)
    if not (e.get("card_name") or "").strip():
        frag = _extract_card_name_fragment(question)
        if frag:
            e["card_name"] = frag
    # LLM may put a long phrase in card_name — prefer regex fragment
    frag2 = _extract_card_name_fragment(question)
    if frag2 and len(frag2) < len(str(e.get("card_name") or "")):
        e["card_name"] = frag2
    cn = (e.get("card_name") or "").strip()
    if cn and memory:
        mem_hit = _fuzzy_card_name_from_memory(cn, memory)
        if mem_hit:
            e["card_name"] = mem_hit
    final = (e.get("card_name") or "").strip()
    if final:
        e["card_name"] = _strip_card_noise(final)
    return e


def _enrich_create_card_entities(question: str, entities: dict[str, Any]) -> dict[str, Any]:
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
    mem = state.get("memory") or {}
    mem_text = memory_summary_for_planner(mem if isinstance(mem, dict) else None)

    llm = get_chat_model(0).with_structured_output(
        PlannerOutput,
        method="function_calling",
    )
    prompt = USER_TEMPLATE.format(question=question, history=history_text, memory=mem_text)
    try:
        raw = invoke_chat_logged(
            llm,
            [
                {"role": "system", "content": _planner_system()},
                {"role": "user", "content": prompt},
            ],
            operation="planner",
        )
        out: PlannerOutput = raw if isinstance(raw, PlannerOutput) else PlannerOutput.model_validate(raw)
    except Exception as e:
        logger.exception("Planner failed")
        return {
            "intent": "planner_error",
            "entities": {},
            "reasoning_trace": f"Planner error: {e}",
            "cleaned_query": question,
            "error_message": str(e),
            "skip_tools": True,
            "needs_clarification": False,
            "clarification_question": "",
            "ambiguous_entities": {},
        }

    if out.needs_clarification and (out.clarification_question or "").strip():
        return {
            "intent": out.intent if out.intent in ALLOWED_INTENTS else "get_boards",
            "entities": dict(out.entities),
            "reasoning_trace": out.reasoning,
            "cleaned_query": question,
            "error_message": "",
            "skip_tools": True,
            "needs_clarification": True,
            "clarification_question": out.clarification_question.strip(),
            "ambiguous_entities": {},
        }

    intent = _coerce_intent(out.intent)
    entities = dict(out.entities)

    intent, entities = _maybe_coerce_board_cards(question, history_lines, intent, entities)
    intent, entities = _maybe_coerce_card_details(question, intent, entities, mem if isinstance(mem, dict) else None)

    if intent == "create_card":
        entities = _enrich_create_card_entities(question, entities)
    if intent == "get_card_details":
        entities = _enrich_card_details_entities(question, entities)
        entities = _refine_card_details_entities(question, entities, mem if isinstance(mem, dict) else None)

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
            "needs_clarification": False,
            "clarification_question": "",
            "ambiguous_entities": {},
        }

    return {
        "intent": intent,
        "entities": entities,
        "reasoning_trace": out.reasoning,
        "cleaned_query": question,
        "error_message": "",
        "skip_tools": False,
        "needs_clarification": False,
        "clarification_question": "",
        "ambiguous_entities": {},
    }
