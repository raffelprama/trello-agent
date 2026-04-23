"""List node."""

from __future__ import annotations

from typing import Any

from app.services.trello_client import TrelloClient, get_client


def create_list(
    board_id: str,
    name: str,
    pos: str | float | None = None,
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_list_on_board(board_id, name, pos=pos)


def get_list(list_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_list(list_id, **params)


def update_list(list_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_list(list_id, **fields)


def archive_list(list_id: str, closed: bool = True, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.archive_list(list_id, closed=closed)


def set_list_closed(list_id: str, value: bool, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.put_list_closed(list_id, value)


def set_list_pos(list_id: str, value: str | float, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.put_list_pos(list_id, value)


def get_list_cards(list_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_list_cards(list_id, **params)


def archive_all_cards(list_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.archive_all_cards_in_list(list_id)


def move_all_cards(list_id: str, body: dict[str, Any], *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.move_all_cards(list_id, body)
