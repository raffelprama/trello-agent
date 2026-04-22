"""Member node — /members/me, boards, cards."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_me(client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_member_me()


def get_my_boards(client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.list_boards(**params)


def update_me(*, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_member_me(**fields)


def get_my_notifications(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_my_notifications(**params)


def get_my_organizations(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_my_organizations(**params)


def get_member_cards(
    member_id: str = "me",
    *,
    client: TrelloClient | None = None,
    **params: Any,
) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_member_cards(member_id, **params)
