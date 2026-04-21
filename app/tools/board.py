"""Board node."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_board(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_board(board_id, **params)


def create_board(
    name: str,
    *,
    desc: str | None = None,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    body: dict[str, Any] = {"name": name}
    if desc is not None:
        body["desc"] = desc
    return c.create_board(body)


def update_board(board_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_board(board_id, **fields)


def get_board_lists(
    board_id: str,
    *,
    cards: str = "none",
    fields: str | None = None,
    client: TrelloClient | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_lists(board_id, cards=cards, fields=fields)


def get_board_cards(
    board_id: str,
    *,
    client: TrelloClient | None = None,
    **params: Any,
) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_cards(board_id, **params)


def get_board_members(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_members(board_id, **params)


def get_board_labels(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_labels(board_id, **params)


def get_board_checklists(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_checklists(board_id, **params)


def get_board_actions(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_actions(board_id, **params)


def create_label(
    board_id: str,
    name: str,
    color: str | None = None,
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_board_label(board_id, name, color=color)
