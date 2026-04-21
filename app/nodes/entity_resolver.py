"""entity_resolver — names → Trello IDs; ambiguity → clarify (PRD v2)."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.state import ChatState
from app.trello_client import get_client

logger = logging.getLogger(__name__)

_INTENTS_NEED_BOARD = frozenset(
    {
        "get_lists",
        "get_cards",
        "get_board_cards",
        "get_card_details",
        "create_card",
        "update_card",
        "move_card",
        "delete_card",
        "get_board",
        "update_board",
        "create_list",
        "update_list",
        "archive_list",
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


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _compact(s: str) -> str:
    return "".join(_norm(s).split())


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


def _find_list(lists: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    n = _norm(name)
    nc = _compact(name or "")
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


def _guess_board_from_question(question: str, boards: list[dict[str, Any]]) -> dict[str, Any] | None:
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
    if not question or not lists:
        return None
    qn = _norm(question)
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


def _pronoun_wants_last_card(question: str) -> bool:
    q = _norm(question)
    return bool(
        re.search(r"\b(that|this|it)\s+card\b", q)
        or q in ("that", "this", "it", "that one", "this one")
        or "the first one" in q
    )


def _collect_all_cards(
    client: Any,
    lists_cache: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_cards: list[dict[str, Any]] = []
    for lst in lists_cache:
        lid = lst.get("id")
        if not lid:
            continue
        stc, cards = client.get_list_cards(str(lid))
        if stc >= 400:
            continue
        lname = lst.get("name")
        for c in cards:
            if isinstance(c, dict):
                cc = dict(c)
                cc["_list_name"] = lname
                all_cards.append(cc)
    return all_cards


def _find_card_id_by_name(name: str, all_cards: list[dict[str, Any]]) -> str | None:
    want = _norm(name)
    if not want:
        return None
    for c in all_cards:
        if _norm(c.get("name")) == want:
            return str(c.get("id")) if c.get("id") else None
    for c in all_cards:
        cn = _norm(c.get("name"))
        if want in cn or cn in want:
            return str(c.get("id")) if c.get("id") else None
    return None


def _cards_matching(name: str, all_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    want = _norm(name)
    if not want:
        return []
    # Prefer exact matches — only fall back to substring when nothing exact exists
    exact = [c for c in all_cards if _norm(c.get("name")) == want]
    if exact:
        return exact
    return [
        c for c in all_cards
        if want in _norm(c.get("name") or "") or _norm(c.get("name") or "") in want
    ]


def _pick_first_card_in_memory_order(
    matches: list[dict[str, Any]],
    memory: dict[str, Any],
) -> dict[str, Any] | None:
    """If several cards match a vague name, prefer the one that appeared first in last_cards (recent listing)."""
    lc = memory.get("last_cards")
    if not isinstance(lc, list) or not matches:
        return None
    want_ids = {str(m.get("id")) for m in matches if m.get("id")}
    for row in lc:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id"))
        if rid in want_ids:
            for m in matches:
                if str(m.get("id")) == rid:
                    return m
    return None


def entity_resolver(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {}

    intent = state.get("intent") or ""
    entities: dict[str, Any] = dict(state.get("entities") or {})
    memory: dict[str, Any] = state.get("memory") or {}
    if not isinstance(memory, dict):
        memory = {}
    question = str(state.get("question") or "")
    client = get_client()

    err: str | None = None

    def _clarify(msg: str, amb: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "error_message": "",
            "entities": entities,
            "skip_tools": True,
            "needs_clarification": True,
            "clarification_question": msg,
            "ambiguous_entities": amb or {},
        }

    try:
        if intent == "get_member_me":
            return {"entities": entities, "error_message": "", "skip_tools": False}

        if intent == "get_boards":
            return {"entities": entities, "error_message": "", "skip_tools": False}

        status, boards = client.list_boards()
        if status >= 400:
            err = f"Failed to list boards: HTTP {status}"
            return {"error_message": err, "entities": entities, "skip_tools": True}

        # Filter closed boards by default
        boards = [b for b in boards if isinstance(b, dict) and not b.get("closed", False)]

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
            if board_name:
                b = _find_board(boards, str(board_name))
                board_id = b["id"] if b else None
                if not board_id:
                    err = f"Board not found: {board_name}"
            elif intent in _INTENTS_NEED_BOARD:
                qtext = question
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
        # Board-only GETs don't need full list cache
        _skip_list_load = frozenset(
            {
                "get_board",
                "get_board_labels",
                "get_board_members",
                "get_board_actions",
            }
        )
        _need_lists = intent in (_INTENTS_NEED_BOARD | {"get_board_cards"}) and intent not in _skip_list_load
        if board_id and _need_lists:
            st, lists_cache = client.get_board_lists(board_id)
            if st >= 400:
                return {"error_message": f"Failed to list lists: HTTP {st}", "entities": entities, "skip_tools": True}
            lists_cache = [x for x in lists_cache if isinstance(x, dict) and not x.get("closed", False)]
            entities["_lists"] = lists_cache

        # Resolve list_id for rename/archive by list name
        if intent in ("update_list", "archive_list") and board_id:
            if entities.get("list_name") and not entities.get("list_id") and lists_cache:
                lst_ul = _find_list(lists_cache, str(entities["list_name"]))
                if lst_ul:
                    entities["list_id"] = lst_ul.get("id")

        all_board_cards: list[dict[str, Any]] = []
        _card_intents = {
            "get_card_details",
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
            "add_card_label",
            "remove_card_label",
        }
        if board_id and lists_cache and intent in _card_intents:
            all_board_cards = _collect_all_cards(client, lists_cache)

        list_name = entities.get("list_name")
        # get_cards: need full card set to detect list-vs-card name collision
        if (
            board_id
            and lists_cache
            and intent == "get_cards"
            and list_name
            and not all_board_cards
        ):
            all_board_cards = _collect_all_cards(client, lists_cache)
        target_list_name = entities.get("target_list_name")
        list_id: str | None = None
        target_list_id: str | None = None

        # --- Ambiguity: get_cards with name that matches both list and card ---
        if intent == "get_cards" and list_name and lists_cache:
            lst_hit = _find_list(lists_cache, str(list_name))
            card_hits = _cards_matching(str(list_name), all_board_cards) if all_board_cards else []
            if lst_hit and card_hits:
                return _clarify(
                    f'I found both a list and a card named "{list_name}". '
                    f'Do you want all cards in the list "{lst_hit.get("name")}", '
                    f'or details for the card "{list_name}"? Reply with "list" or "card".',
                    {
                        "kind": "list_or_card",
                        "name": list_name,
                        "list_id": lst_hit.get("id"),
                        "card_ids": [c.get("id") for c in card_hits],
                    },
                )

        if list_name and lists_cache:
            lst = _find_list(lists_cache, str(list_name))
            list_id = lst["id"] if lst else None
            if not list_id and intent in ("get_cards", "create_card"):
                # Maybe user meant a card — check cards
                if all_board_cards:
                    cmatches = _cards_matching(str(list_name), all_board_cards)
                    if len(cmatches) == 1:
                        return _clarify(
                            f'There is no list named "{list_name}", but there is a card with that name '
                            f'in "{cmatches[0].get("_list_name")}". '
                            f'Did you mean to open that card? Reply "yes" or say "list" + the column name.',
                            {"kind": "list_not_found_but_card", "card_name": list_name},
                        )
                err = err or f"List not found: {list_name}"

        if (
            not list_id
            and not err
            and lists_cache
            and intent == "create_card"
        ):
            guessed = _guess_list_from_question(question, lists_cache)
            if guessed and guessed.get("id"):
                list_id = str(guessed["id"])

        entities["list_id"] = list_id

        if target_list_name and lists_cache:
            tl = _find_list(lists_cache, str(target_list_name))
            target_list_id = tl["id"] if tl else None
            if not target_list_id and intent == "move_card":
                available = ", ".join(str(x.get("name")) for x in lists_cache[:15])
                return _clarify(
                    f'I couldn\'t find a list named "{target_list_name}". '
                    f"Available lists: {available}. "
                    "Which list would you like to move the card to?",
                    {"kind": "target_list_not_found", "target_list_name": target_list_name},
                )
        elif intent == "move_card" and not target_list_name and lists_cache:
            available = ", ".join(str(x.get("name")) for x in lists_cache[:15])
            return _clarify(
                f"Which list would you like to move the card to? "
                f"Available lists: {available}.",
                {"kind": "target_list_missing"},
            )
        entities["target_list_id"] = target_list_id

        card_name = entities.get("card_name")
        card_id: str | None = entities.get("card_id")  # type: ignore[assignment]

        logger.debug(
            "[resolver] start card resolution | intent=%s card_name=%r card_id=%r",
            intent, card_name, card_id,
        )

        # If the user typed a raw 24-char hex Trello card ID, use it immediately (card intents only)
        _intents_accept_raw_id = {
            "get_card_details", "update_card", "move_card", "delete_card",
            "get_card_checklists", "create_checklist", "delete_checklist",
            "get_checkitems", "create_checkitem", "check_item", "uncheck_item",
            "delete_checkitem", "get_comments", "create_comment",
            "add_card_label", "remove_card_label",
        }
        if intent in _intents_accept_raw_id and not card_id:
            _hex_id_pat = re.compile(r"\b([0-9a-f]{24})\b", re.IGNORECASE)
            m_hex = _hex_id_pat.search(question)
            if m_hex:
                card_id = m_hex.group(1).lower()
                entities["card_id"] = card_id
                logger.info("[resolver] card_id extracted from raw hex in message: %s", card_id)

        # Pronouns → last card from memory
        if not card_name and _pronoun_wants_last_card(question):
            mid = memory.get("last_card_id")
            if mid:
                card_id = str(mid)
                entities["card_name"] = memory.get("last_card_name")
                logger.debug("[resolver] card_id from pronoun+memory: %s name=%r", card_id, entities["card_name"])

        # Memory fallback for card name
        if card_name and not card_id and memory.get("last_cards"):
            lc = memory["last_cards"]
            if isinstance(lc, list):
                want = _norm(str(card_name))
                for row in lc:
                    if not isinstance(row, dict):
                        continue
                    if _norm(str(row.get("name"))) == want and row.get("id"):
                        card_id = str(row["id"])
                        logger.debug("[resolver] card_id from memory fallback: %s (matched %r)", card_id, row.get("name"))
                        break

        intents_need_card = {
            "get_card_details",
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
            "add_card_label",
            "remove_card_label",
        }

        # --- Resolve pending clarification from previous turn ---
        pending = memory.get("pending_clarify") or {}
        pending_amb = (pending.get("ambiguous") or {})
        logger.debug("[resolver] pending_clarify kind=%r", pending_amb.get("kind"))

        if pending_amb.get("kind") == "multiple_cards" and not card_id:
            candidates = [m for m in (pending_amb.get("matches") or []) if isinstance(m, dict)]
            logger.debug("[resolver] multiple_cards candidates=%d card_name=%r list_name=%r", len(candidates), card_name, list_name)
            if candidates:
                if card_name:
                    exact_cands = [m for m in candidates if _norm(str(m.get("name"))) == _norm(str(card_name))]
                    logger.debug("[resolver] exact candidate hits=%d", len(exact_cands))
                    if len(exact_cands) == 1:
                        card_id = str(exact_cands[0]["id"])
                        entities["card_id"] = card_id
                        logger.debug("[resolver] resolved via pending exact: %s", card_id)
                if not card_id and list_name:
                    list_filtered = [m for m in candidates if _norm(str(m.get("list"))) == _norm(str(list_name))]
                    logger.debug("[resolver] list-filtered candidate hits=%d", len(list_filtered))
                    if len(list_filtered) == 1:
                        card_id = str(list_filtered[0]["id"])
                        card_name = list_filtered[0].get("name")
                        entities["card_id"] = card_id
                        entities["card_name"] = card_name
                        logger.debug("[resolver] resolved via pending list filter: %s name=%r", card_id, card_name)

        if pending_amb.get("kind") == "card_name_missing" and not card_name and not card_id:
            q = question.strip().strip('"').strip("'")
            m_cn = re.search(
                r'(?:card\s+(?:name\s+)?is|name\s+is|it[\'s\s]+(?:called|named?))\s+["\']?([^"\']+?)["\']?\s*$',
                q,
                re.IGNORECASE,
            )
            if m_cn:
                card_name = m_cn.group(1).strip().strip('"').strip("'")
                entities["card_name"] = card_name
                logger.debug("[resolver] card_name from 'name is X' pattern: %r", card_name)
            elif len(q.split()) <= 5:
                # Treat short response as the card name; strip noise words
                candidate = re.sub(r"^(?:the\s+)?card\s+", "", q, flags=re.IGNORECASE).strip().strip('"').strip("'")
                candidate = candidate or q
                if candidate:
                    card_name = candidate
                    entities["card_name"] = card_name
                    logger.debug("[resolver] card_name from short reply: %r", card_name)

        logger.debug(
            "[resolver] pre-guard | card_name=%r card_id=%r intent=%s needs_card=%s",
            card_name, card_id, intent, intent in intents_need_card,
        )

        # Guard: card name still missing after all resolution attempts
        if not card_name and not card_id and intent in intents_need_card and not err:
            if pending_amb.get("kind") != "card_name_missing":
                logger.info("[resolver] firing card_name_missing clarification (card_name=%r card_id=%r)", card_name, card_id)
                return _clarify(
                    "Which card are you referring to? Please provide the card name.",
                    {"kind": "card_name_missing"},
                )
            # Already asked once — give up to avoid an infinite loop
            logger.debug("[resolver] card_name_missing loop detected — giving up")
            return {
                "error_message": (
                    "I couldn't identify the card. "
                    "Try phrasing like: 'show me the Ai2 card' or 'open card Ai2 in On Going'."
                ),
                "entities": entities,
                "skip_tools": True,
            }

        if card_name and board_id and intent in intents_need_card:
            if not lists_cache:
                st, lists_cache = client.get_board_lists(board_id)
                if st >= 400:
                    return {"error_message": f"Failed to list lists: HTTP {st}", "entities": entities, "skip_tools": True}
                lists_cache = [x for x in lists_cache if isinstance(x, dict) and not x.get("closed", False)]
                entities["_lists"] = lists_cache
            if not all_board_cards:
                all_board_cards = _collect_all_cards(client, lists_cache)
            logger.debug("[resolver] _cards_matching query=%r total_cards=%d", card_name, len(all_board_cards))
            matches = _cards_matching(str(card_name), all_board_cards)
            logger.info(
                "[resolver] _cards_matching(%r) hits=%d: %s",
                card_name,
                len(matches),
                [(m.get("name"), m.get("_list_name"), (m.get("id") or "")[:8]) for m in matches[:5]],
            )
            if len(matches) > 1:
                mem_pick = _pick_first_card_in_memory_order(matches, memory)
                if mem_pick:
                    logger.debug("[resolver] memory-order pick: %r", mem_pick.get("name"))
                    matches = [mem_pick]
            if len(matches) > 1:
                names = ", ".join(
                    f"{m.get('name')} (list: {m.get('_list_name')})" for m in matches[:5]
                )
                logger.info("[resolver] ambiguous multiple_cards — asking clarification: %s", names)
                return _clarify(
                    f"Multiple cards match \"{card_name}\": {names}. Which one did you mean? "
                    f"Reply with the full card title and optionally the list name.",
                    {
                        "kind": "multiple_cards",
                        "matches": [
                            {"id": m.get("id"), "name": m.get("name"), "list": m.get("_list_name")}
                            for m in matches[:5]
                        ],
                    },
                )
            if len(matches) == 1:
                card_id = str(matches[0].get("id")) if matches[0].get("id") else None
                logger.info("[resolver] card resolved → name=%r id=%s list=%r", matches[0].get("name"), card_id, matches[0].get("_list_name"))
            else:
                card_id = _find_card_id_by_name(str(card_name), all_board_cards)
                logger.info("[resolver] _find_card_id_by_name(%r) → %s", card_name, card_id)
            if not card_id:
                cards_hint = ", ".join(str(c.get("name")) for c in all_board_cards[:15]) if all_board_cards else "(none found)"
                logger.info("[resolver] card NOT found for %r — board has: %s", card_name, cards_hint)
                return _clarify(
                    f'I couldn\'t find a card named "{card_name}". '
                    f"Cards on this board: {cards_hint}. "
                    "Which card did you mean?",
                    {"kind": "card_not_found", "card_name": card_name},
                )
        logger.info("[resolver] resolved | card_name=%r card_id=%s board=%r", card_name, card_id, entities.get("resolved_board_name"))
        entities["card_id"] = card_id

        # Checklist / checkitem resolution (by name) — need card_id first
        checklist_name = entities.get("checklist_name")
        check_item_name = entities.get("check_item_name")

        if intent in (
            "get_checkitems",
            "create_checkitem",
            "check_item",
            "uncheck_item",
            "delete_checkitem",
            "delete_checklist",
        ) and card_id and checklist_name:
            st_ch, chs = client.get_card_checklists(str(card_id))
            if st_ch >= 400:
                err = err or f"Failed to get checklists: HTTP {st_ch}"
            else:
                entities["_checklists"] = chs if isinstance(chs, list) else []
                ch_hit = None
                for ch in entities["_checklists"]:
                    if isinstance(ch, dict) and _norm(str(ch.get("name"))) == _norm(str(checklist_name)):
                        ch_hit = ch
                        break
                    if isinstance(ch, dict) and _norm(str(checklist_name)) in _norm(str(ch.get("name"))):
                        ch_hit = ch
                if ch_hit:
                    entities["checklist_id"] = ch_hit.get("id")
                elif not err:
                    err = f"Checklist not found: {checklist_name}"

                if entities.get("checklist_id") and check_item_name and intent in (
                    "check_item",
                    "uncheck_item",
                    "delete_checkitem",
                ):
                    cid_ch = str(entities["checklist_id"])
                    sti, items = client.get_checklist_check_items(cid_ch)
                    if sti >= 400:
                        err = err or f"Failed to get check items: HTTP {sti}"
                    else:
                        it_hit = None
                        for it in items or []:
                            if isinstance(it, dict) and _norm(str(it.get("name"))) == _norm(str(check_item_name)):
                                it_hit = it
                                break
                            if isinstance(it, dict) and _norm(str(check_item_name)) in _norm(str(it.get("name"))):
                                it_hit = it
                        if it_hit:
                            entities["check_item_id"] = it_hit.get("id")
                        elif not err:
                            err = f"Check item not found: {check_item_name}"

        # Label resolution by name on board
        label_name = entities.get("label_name")
        if intent in ("add_card_label", "remove_card_label") and board_id and label_name and not entities.get("label_id"):
            stl, labels = client.get_board_labels(board_id)
            if stl >= 400:
                err = err or f"Failed to list labels: HTTP {stl}"
            else:
                for lb in labels or []:
                    if isinstance(lb, dict) and _norm(str(lb.get("name"))) == _norm(str(label_name)):
                        entities["label_id"] = lb.get("id")
                        break
                if not entities.get("label_id") and not err:
                    err = f"Label not found: {label_name}"

        # move_card idempotency hint (optional fields for executor)
        if intent == "move_card" and card_id and target_list_id:
            st_cd, cdetail = client.get_card(str(card_id), params={"fields": "idList"})
            if st_cd < 400 and isinstance(cdetail, dict):
                if str(cdetail.get("idList")) == str(target_list_id):
                    entities["_already_in_target_list"] = True

        if err:
            # Prefer clarification for "not found" when we can ask
            if "List not found" in err and list_name:
                return _clarify(
                    f'I couldn\'t find a list named "{list_name}". '
                    f'Available lists: {", ".join(str(x.get("name")) for x in lists_cache[:15])}. '
                    f"Which list did you mean?",
                    {"kind": "list_not_found", "list_name": list_name},
                )
            return {"error_message": err, "entities": entities, "skip_tools": True}

        return {"entities": entities, "error_message": "", "skip_tools": False}

    except Exception as e:
        logger.exception("entity_resolver")
        return {"error_message": str(e), "entities": entities, "skip_tools": True}
