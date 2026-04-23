"""CardAgent set_card_due_complete idempotency."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.trello.card import CardAgent


def test_set_card_due_complete_skips_when_already_set(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def get_details(cid: str) -> tuple[int, dict]:
        return 200, {"id": cid, "dueComplete": True}

    def set_due_complete(cid: str, dc: bool) -> tuple[int, dict]:
        calls.append((cid, dc))
        return 200, {"id": cid, "dueComplete": dc}

    monkeypatch.setattr("app.agents.trello.card.card_tools.get_card_details", get_details)
    monkeypatch.setattr("app.agents.trello.card.card_tools.set_due_complete", set_due_complete)

    agent = CardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="card",
        ask="set_card_due_complete",
        context={"_resolved_inputs": {"card_id": "c1", "dueComplete": True}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("skipped") is True
    assert r.data.get("reason") == "already_in_state"
    assert calls == []


def test_set_card_due_complete_calls_api_when_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def get_details(cid: str) -> tuple[int, dict]:
        return 200, {"id": cid, "dueComplete": False}

    def set_due_complete(cid: str, dc: bool) -> tuple[int, dict]:
        calls.append((cid, dc))
        return 200, {"id": cid, "dueComplete": dc}

    monkeypatch.setattr("app.agents.trello.card.card_tools.get_card_details", get_details)
    monkeypatch.setattr("app.agents.trello.card.card_tools.set_due_complete", set_due_complete)

    agent = CardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="card",
        ask="set_card_due_complete",
        context={"_resolved_inputs": {"card_id": "c1", "dueComplete": True}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("skipped") is not True
    assert calls == [("c1", True)]
