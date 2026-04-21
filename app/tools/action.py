"""Action / comment node."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_action(action_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_action(action_id, **params)


def update_comment(action_id: str, text: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_action_comment(action_id, text)


def delete_comment(action_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_action(action_id)


def get_card_actions(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_actions(card_id, **params)


def get_board_actions(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_actions(board_id, **params)


def post_comment(card_id: str, text: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.post_card_comment(card_id, text)
