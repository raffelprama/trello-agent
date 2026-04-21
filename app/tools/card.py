"""Card node."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_card(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_card(card_id, **params)


def get_card_details(card_id: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_card_details(card_id)


def create_card(
    id_list: str,
    name: str,
    desc: str | None = None,
    due: str | None = None,
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_card(id_list, name, desc=desc, due=due)


def update_card(card_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_card(card_id, **fields)


def move_card(card_id: str, id_list: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.move_card(card_id, id_list)


def delete_card(card_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_card(card_id)


def get_card_checklists(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_checklists(card_id, **params)


def post_card_checklist(card_id: str, name: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.post_card_checklist(card_id, name)


def get_card_actions(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_actions(card_id, **params)


def get_card_attachments(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_attachments(card_id, **params)


def post_comment(card_id: str, text: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.post_card_comment(card_id, text)


def add_member(card_id: str, member_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.post_card_member(card_id, member_id)


def add_label(card_id: str, label_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.post_card_label(card_id, label_id)


def remove_label(card_id: str, label_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_card_label(card_id, label_id)


def set_due(card_id: str, due: str | None, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.put_card_due(card_id, due)


def set_due_complete(card_id: str, due_complete: bool, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.put_card_due_complete(card_id, due_complete)
