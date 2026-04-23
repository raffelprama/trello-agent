"""Shrink Trello API dicts before LLM prompts (full board payloads are 5–15k+ tokens each)."""

from __future__ import annotations

from typing import Any


def slim_board(board: dict[str, Any] | None) -> dict[str, Any] | None:
    if not board or not isinstance(board, dict):
        return None
    return {
        "id": board.get("id"),
        "name": board.get("name"),
        "closed": board.get("closed"),
        "url": board.get("shortUrl") or board.get("url"),
        "starred": board.get("starred"),
        "dateLastActivity": board.get("dateLastActivity"),
    }


def slim_boards(boards: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for b in boards:
        if not isinstance(b, dict):
            continue
        s = slim_board(b)
        if s is not None:
            out.append(s)
    return out


def slim_card(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not card or not isinstance(card, dict):
        return None
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "idList": card.get("idList"),
        "due": card.get("due"),
        "dueComplete": card.get("dueComplete"),
        "closed": card.get("closed"),
    }


def slim_cards(cards: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        s = slim_card(c)
        if s is not None:
            out.append(s)
    return out


def slim_result_for_answer(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with large Trello collections replaced by slim rows."""
    d = dict(data)
    if isinstance(d.get("boards"), list):
        d["boards"] = slim_boards(d["boards"])
    if isinstance(d.get("board"), dict):
        sb = slim_board(d["board"])
        if sb is not None:
            d["board"] = sb
    if isinstance(d.get("cards"), list):
        d["cards"] = slim_cards(d["cards"])
    return d
