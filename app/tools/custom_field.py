"""Custom field definitions (board) and values (card) — PRD v3 §6.10."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_board_custom_fields(board_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_board_custom_fields(board_id, **params)


def create_custom_field(
    board_id: str,
    body: dict[str, Any],
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_custom_field(board_id, body)


def update_custom_field(custom_field_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_custom_field(custom_field_id, **fields)


def delete_custom_field(custom_field_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_custom_field(custom_field_id)


def get_custom_field_options(custom_field_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_custom_field_options(custom_field_id, **params)


def add_custom_field_option(custom_field_id: str, text: str, *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.add_custom_field_option(custom_field_id, text)


def delete_custom_field_option(custom_field_id: str, option_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_custom_field_option(custom_field_id, option_id)


def get_card_custom_field_items(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_custom_field_items(card_id, **params)


def set_card_custom_field_item(
    card_id: str,
    custom_field_id: str,
    body: dict[str, Any],
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.set_card_custom_field_item(card_id, custom_field_id, body)
