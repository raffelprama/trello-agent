"""Checklist node — check item state via /cards/{id}/checkItem/{id}."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_checklist(checklist_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_checklist(checklist_id, **params)


def update_checklist(checklist_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_checklist(checklist_id, **fields)


def delete_checklist(checklist_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_checklist(checklist_id)


def get_checkitems(checklist_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_checklist_check_items(checklist_id, **params)


def create_checkitem(
    checklist_id: str,
    name: str,
    pos: str | None = "bottom",
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_check_item(checklist_id, name, pos=pos)


def delete_checkitem(checklist_id: str, check_item_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_check_item(checklist_id, check_item_id)


def set_checkitem_state(
    card_id: str,
    check_item_id: str,
    state: str,
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    """state: 'complete' | 'incomplete'."""
    c = client or get_client()
    return c.put_check_item_state(card_id, check_item_id, state)
