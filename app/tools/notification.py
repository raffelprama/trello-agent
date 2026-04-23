"""Notifications — PRD v3 §6.14."""

from __future__ import annotations

from typing import Any

from app.services.trello_client import TrelloClient, get_client


def get_my_notifications(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_my_notifications(**params)


def get_notification(notification_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_notification(notification_id, **params)


def update_notification(notification_id: str, *, client: TrelloClient | None = None, **fields: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_notification(notification_id, **fields)


def mark_all_notifications_read(*, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.mark_all_notifications_read()
