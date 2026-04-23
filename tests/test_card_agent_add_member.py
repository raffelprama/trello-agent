"""CardAgent add_card_member."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.trello.card import CardAgent


def test_add_card_member_need_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.trello.card.card_tools.get_card_details",
        lambda cid: (200, {"id": cid, "idMembers": []}),
    )
    agent = CardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="card",
        ask="add_card_member",
        context={"_resolved_inputs": {"card_id": "c1"}},
    )
    r = agent.handle(msg)
    assert r.status == "need_info"
    assert "member_id" in r.missing

    msg2 = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="card",
        ask="add_card_member",
        context={"_resolved_inputs": {"member_id": "m1"}},
    )
    r2 = agent.handle(msg2)
    assert r2.status == "need_info"
    assert "card_id" in r2.missing


def test_add_card_member_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[tuple[str, str]] = []

    def get_details(cid: str) -> tuple[int, dict]:
        if not added:
            return 200, {"id": cid, "idMembers": []}
        return 200, {"id": cid, "idMembers": ["m1"]}

    def add_member(cid: str, mid: str) -> tuple[int, object]:
        added.append((cid, mid))
        return 200, {}

    monkeypatch.setattr("app.agents.trello.card.card_tools.get_card_details", get_details)
    monkeypatch.setattr("app.agents.trello.card.card_tools.add_member", add_member)

    agent = CardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="card",
        ask="add_card_member",
        context={"_resolved_inputs": {"card_id": "c1", "member_id": "m1"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert added == [("c1", "m1")]
