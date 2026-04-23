"""Card attachments (URL) — PRD v3 §6.9."""

from __future__ import annotations

from typing import Any

from app.services.trello_client import TrelloClient, get_client


def list_attachments(card_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_card_attachments(card_id, **params)


def get_attachment(card_id: str, attachment_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_card_attachment(card_id, attachment_id, **params)


def add_url_attachment(
    card_id: str,
    url: str,
    *,
    name: str | None = None,
    mime_type: str | None = None,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.post_card_attachment_url(card_id, url, name=name, mime_type=mime_type)


def delete_attachment(card_id: str, attachment_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_card_attachment(card_id, attachment_id)
