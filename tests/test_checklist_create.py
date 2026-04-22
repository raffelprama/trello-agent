"""ChecklistAgent create_checklist."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.checklist import ChecklistAgent


def test_create_checklist_need_info(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="create_checklist",
        context={"_resolved_inputs": {"name": "Groceries"}},
    )
    r = agent.handle(msg)
    assert r.status == "need_info"
    assert "card_id" in r.missing

    msg2 = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="create_checklist",
        context={"_resolved_inputs": {"card_id": "c1"}},
    )
    r2 = agent.handle(msg2)
    assert r2.status == "need_info"
    assert "name" in r2.missing


def test_create_checklist_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def post_checklist(cid: str, name: str) -> tuple[int, dict]:
        return 200, {"id": "cl-new", "name": name, "idCard": cid}

    monkeypatch.setattr("app.agents.checklist.card_tools.post_card_checklist", post_checklist)

    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="create_checklist",
        context={"_resolved_inputs": {"card_id": "c1", "name": "Todo"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("checklist_id") == "cl-new"
