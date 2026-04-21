"""Member node — /members/me, boards, cards."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_me(client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_member_me()


def get_my_boards(client: TrelloClient | None = None) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.list_boards()


def get_member_cards(
    member_id: str = "me",
    *,
    client: TrelloClient | None = None,
    **params: Any,
) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_member_cards(member_id, **params)
