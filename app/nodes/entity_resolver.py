"""entity_resolver — names → Trello IDs (no cross-session cache)."""

from __future__ import annotations

import logging
from typing import Any

from app.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.state import ChatState
from app.trello_client import get_client

logger = logging.getLogger(__name__)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _find_board(boards: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    n = _norm(name)
    for b in boards:
        if _norm(b.get("name")) == n:
            return b
    for b in boards:
        if n in _norm(b.get("name")):
            return b
    return None


def _compact(s: str) -> str:
    """Compare names when spaces differ, e.g. 'on going' vs 'ongoing'."""
    return "".join(_norm(s).split())


def _find_list(lists: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    n = _norm(name)
    nc = _compact(name)
    for lst in lists:
        ln = _norm(lst.get("name"))
        if ln == n:
            return lst
    for lst in lists:
        lname = lst.get("name")
        lnn = _norm(lname)
        if n in lnn or lnn in n:
            return lst
    if nc and len(nc) >= 3:
        for lst in lists:
            if _compact(str(lst.get("name"))) == nc:
                return lst
    return None


def _guess_board_from_question(
    question: str, boards: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Match a board display name as substring in the user message (when planner omits board_name)."""
    if not question or not boards:
        return None
    qn = _norm(question)
    ranked = sorted(
        [b for b in boards if isinstance(b, dict) and (b.get("name") or "").strip()],
        key=lambda x: len(_norm(str(x.get("name")))),
        reverse=True,
    )
    for b in ranked:
        bn = _norm(str(b.get("name")))
        if len(bn) < 3:
            continue
        if bn in qn:
            return b
    return None


def _guess_list_from_question(question: str, lists: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match board list display names as substrings in the user message (handles missing list_name)."""
    if not question or not lists:
        return None
    qn = _norm(question)
    # Prefer longer names first so 'On Going' wins over 'List'
    ranked = sorted(
        [x for x in lists if isinstance(x, dict) and (x.get("name") or "").strip()],
        key=lambda x: len(_norm(str(x.get("name")))),
        reverse=True,
    )
    for lst in ranked:
        ln = _norm(str(lst.get("name")))
        if len(ln) < 2:
            continue
        if ln in qn:
            return lst
    return None


def entity_resolver(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {}

    intent = state.get("intent") or ""
    entities: dict[str, Any] = dict(state.get("entities") or {})
    client = get_client()

    err: str | None = None

    try:
        status, boards = client.list_boards()
        if status >= 400:
            err = f"Failed to list boards: HTTP {status}"
            return {"error_message": err, "entities": entities, "skip_tools": True}

        _INTENTS_NEED_BOARD = (
            "get_lists",
            "get_cards",
            "get_board_cards",
            "get_card_details",
            "create_card",
            "update_card",
            "move_card",
            "delete_card",
        )

        board_name = entities.get("board_name")
        board_id: str | None = None
        scoped_id = TRELLO_BOARD_ID

        if BOARD_SCOPE_ONLY and scoped_id:
            scoped_board = next((b for b in boards if b.get("id") == scoped_id), None)
            if not scoped_board:
                return {
                    "error_message": (
                        "TRELLO_BOARD_ID is not among boards this token can access; "
                        "check the ID and permissions."
                    ),
                    "entities": entities,
                    "skip_tools": True,
                }

            if board_name:
                b = _find_board(boards, str(board_name))
                if not b:
                    err = f"Board not found: {board_name}"
                elif b.get("id") != scoped_id:
                    err = (
                        f'Only board "{scoped_board.get("name")}" is available here '
                        "(single-board mode: TRELLO_BOARD_ID)."
                    )
                else:
                    board_id = scoped_id
            elif intent in _INTENTS_NEED_BOARD:
                board_id = scoped_id
        else:
            default_board_id = TRELLO_BOARD_ID
            if default_board_id and not any(b.get("id") == default_board_id for b in boards):
                pass

            if board_name:
                b = _find_board(boards, str(board_name))
                board_id = b["id"] if b else None
                if not board_id:
                    err = f"Board not found: {board_name}"
            elif intent in _INTENTS_NEED_BOARD:
                qtext = str(state.get("question") or "")
                guessed_b = _guess_board_from_question(qtext, boards)
                if guessed_b and guessed_b.get("id"):
                    board_id = str(guessed_b["id"])
                    entities["board_name"] = guessed_b.get("name")
                elif default_board_id:
                    board_id = default_board_id
                elif len(boards) == 1:
                    board_id = boards[0]["id"]
                elif intent != "get_boards":
                    err = "Specify a board name or set TRELLO_BOARD_ID in .env"

        entities["board_id"] = board_id

        if board_id and not err:
            rb = next(
                (b for b in boards if isinstance(b, dict) and b.get("id") == board_id),
                None,
            )
            if rb:
                entities["resolved_board_name"] = rb.get("name")

        lists_cache: list[dict[str, Any]] = []
        if board_id and intent in (
            "get_lists",
            "get_cards",
            "get_board_cards",
            "get_card_details",
            "create_card",
            "update_card",
            "move_card",
            "delete_card",
        ):
            st, lists_cache = client.get_board_lists(board_id)
            if st >= 400:
                return {"error_message": f"Failed to list lists: HTTP {st}", "entities": entities, "skip_tools": True}
            entities["_lists"] = lists_cache

        list_name = entities.get("list_name")
        target_list_name = entities.get("target_list_name")
        list_id: str | None = None
        target_list_id: str | None = None

        if list_name and lists_cache:
            lst = _find_list(lists_cache, str(list_name))
            list_id = lst["id"] if lst else None
            if not list_id and intent in ("get_cards", "create_card"):
                err = f"List not found: {list_name}"

        if (
            not list_id
            and not err
            and lists_cache
            and intent == "create_card"
        ):
            guessed = _guess_list_from_question(
                str(state.get("question") or ""),
                lists_cache,
            )
            if guessed and guessed.get("id"):
                list_id = str(guessed["id"])

        entities["list_id"] = list_id

        if target_list_name and lists_cache:
            tl = _find_list(lists_cache, str(target_list_name))
            target_list_id = tl["id"] if tl else None
            if not target_list_id and intent == "move_card":
                err = err or f"Target list not found: {target_list_name}"
        entities["target_list_id"] = target_list_id

        card_name = entities.get("card_name")
        card_id: str | None = entities.get("card_id")  # type: ignore[assignment]

        def _find_card_id_by_name(name: str, lists: list[dict[str, Any]]) -> str | None:
            want = _norm(name)
            if not want:
                return None
            all_cards: list[dict[str, Any]] = []
            for lst in lists:
                lid = lst.get("id")
                if not lid:
                    continue
                stc, cards = client.get_list_cards(str(lid))
                if stc >= 400:
                    continue
                for c in cards:
                    if isinstance(c, dict):
                        all_cards.append(c)
            for c in all_cards:
                if _norm(c.get("name")) == want:
                    return str(c.get("id"))
            for c in all_cards:
                cn = _norm(c.get("name"))
                if want in cn or cn in want:
                    return str(c.get("id"))
            return None

        if card_name and board_id and intent in (
            "update_card",
            "move_card",
            "delete_card",
            "get_card_details",
        ):
            if not lists_cache:
                st, lists_cache = client.get_board_lists(board_id)
                if st >= 400:
                    return {"error_message": f"Failed to list lists: HTTP {st}", "entities": entities, "skip_tools": True}
            found = _find_card_id_by_name(str(card_name), lists_cache)
            card_id = found
            if not card_id:
                err = err or f"Card not found: {card_name}"
        entities["card_id"] = card_id

        if err:
            return {"error_message": err, "entities": entities, "skip_tools": True}

        return {"entities": entities, "error_message": "", "skip_tools": False}

    except Exception as e:
        logger.exception("entity_resolver")
        return {"error_message": str(e), "entities": entities, "skip_tools": True}
