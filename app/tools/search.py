"""Search — PRD v3 §6.13."""

from __future__ import annotations

from typing import Any

from app.services.trello_client import TrelloClient, get_client


def search_trello(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.search(**params)


def search_members(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.search_members(**params)
