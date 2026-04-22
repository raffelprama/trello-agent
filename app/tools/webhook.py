"""Webhooks — PRD v3 §6.11."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def list_webhooks(*, client: TrelloClient | None = None) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.list_token_webhooks()


def create_webhook(body: dict[str, Any], *, client: TrelloClient | None = None) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.create_webhook(body)


def get_webhook(webhook_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_webhook(webhook_id, **params)


def update_webhook(webhook_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_webhook(webhook_id, **fields)


def delete_webhook(webhook_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.delete_webhook(webhook_id)
