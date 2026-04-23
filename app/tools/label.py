"""Label node."""

from __future__ import annotations

from typing import Any

from app.services.trello_client import TrelloClient, get_client


def get_label(label_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_label(label_id, **params)


def update_label(label_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_label(label_id, **fields)


def delete_label(label_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_label(label_id)
