"""MemberAgent resolve_member."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.member import MemberAgent


def test_resolve_member_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    members = [
        {"id": "m1", "fullName": "Alice Jones", "username": "ajones"},
        {"id": "m2", "fullName": "Bob Smith", "username": "bsmith"},
    ]

    monkeypatch.setattr(
        "app.agents.member.board_tools.get_board_members",
        lambda bid: (200, members),
    )

    agent = MemberAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="member",
        ask="resolve_member",
        context={"_resolved_inputs": {"board_id": "b1", "member_hint": "Alice Jones"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("member_id") == "m1"


def test_resolve_member_levenshtein(monkeypatch: pytest.MonkeyPatch) -> None:
    members = [
        {"id": "m1", "fullName": "Planning Team", "username": "pteam"},
    ]

    monkeypatch.setattr(
        "app.agents.member.board_tools.get_board_members",
        lambda bid: (200, members),
    )

    agent = MemberAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="member",
        ask="resolve_member",
        context={"_resolved_inputs": {"board_id": "b1", "member_hint": "Planing"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("member_id") == "m1"


def test_resolve_member_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    members = [
        {"id": "m1", "fullName": "Alice One", "username": "a1"},
        {"id": "m2", "fullName": "Alice Two", "username": "a2"},
    ]

    monkeypatch.setattr(
        "app.agents.member.board_tools.get_board_members",
        lambda bid: (200, members),
    )

    agent = MemberAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="member",
        ask="resolve_member",
        context={"_resolved_inputs": {"board_id": "b1", "member_hint": "Alice"}},
    )
    r = agent.handle(msg)
    assert r.status == "clarify_user"
    assert len(r.data.get("candidates") or []) >= 2
