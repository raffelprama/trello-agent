"""Organizations / workspaces — PRD v3 §6.12."""

from __future__ import annotations

from typing import Any

from app.trello_client import TrelloClient, get_client


def get_my_organizations(*, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_my_organizations(**params)


def get_organization(org_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.get_organization(org_id, **params)


def get_organization_boards(org_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_organization_boards(org_id, **params)


def get_organization_members(org_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_organization_members(org_id, **params)


def get_organization_memberships(org_id: str, *, client: TrelloClient | None = None, **params: Any) -> tuple[int, list[dict[str, Any]]]:
    c = client or get_client()
    return c.get_organization_memberships(org_id, **params)


def update_organization_member(
    org_id: str,
    member_id: str,
    member_type: str,
    *,
    client: TrelloClient | None = None,
) -> tuple[int, dict[str, Any]]:
    c = client or get_client()
    return c.update_organization_member(org_id, member_id, member_type)


def remove_organization_member(org_id: str, member_id: str, *, client: TrelloClient | None = None) -> tuple[int, Any]:
    c = client or get_client()
    return c.remove_organization_member(org_id, member_id)
