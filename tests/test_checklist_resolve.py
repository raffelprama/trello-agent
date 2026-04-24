"""Checklist name resolution and scoped check-item resolve."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.trello.checklist import ChecklistAgent


def test_resolve_checklist_unique_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"id": "c1", "name": "Implementation"}, {"id": "c2", "name": "QA"}]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={"_resolved_inputs": {"card_id": "card1", "checklist_name": "Implementation"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("checklist_id") == "c1"
    assert r.data.get("created") is False


def test_resolve_checklist_ambiguous_substring_clarifies(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"id": "a", "name": "Dev Implementation"}, {"id": "b", "name": "QA Implementation"}]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={"_resolved_inputs": {"card_id": "card1", "checklist_name": "implementation"}},
    )
    r = agent.handle(msg)
    assert r.status == "clarify_user"
    assert "candidates" in r.data


def test_resolve_check_item_prefers_checklist_name_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_cl(_cid: str) -> tuple[int, list]:
        return (
            200,
            [
                {"id": "cl1", "name": "Implementation"},
                {"id": "cl2", "name": "Other"},
            ],
        )

    def get_items(clid: str) -> tuple[int, list]:
        if clid == "cl1":
            return (200, [{"id": "i1", "name": "Integrate Langraph and Langchain"}, {"id": "i2", "name": "Ship"}])
        return (200, [{"id": "i3", "name": "Integrate Langraph and Langchain"}])

    monkeypatch.setattr("app.agents.trello.checklist.card_tools.get_card_checklists", get_cl)
    monkeypatch.setattr("app.agents.trello.checklist.cl_tools.get_checkitems", get_items)

    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_check_item",
        context={
            "_resolved_inputs": {
                "card_id": "card1",
                "checklist_name": "Implementation",
                "item_name": "Integrate Langraph and Langchain",
            }
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("check_item_id") == "i1"
    assert r.data.get("checkitem_id") == "i1"
    assert r.data.get("checklist_id") == "cl1"


def test_resolve_checklist_infers_checklist_from_item_name(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "id": "cl_plan",
            "name": "Project Planning",
            "checkItems": [{"id": "i1", "name": "Define goals"}],
        },
        {
            "id": "cl_dev",
            "name": "Website Development",
            "checkItems": [
                {"id": "i2", "name": "Set up basic SEO (meta tags, alt text, page titles)"},
            ],
        },
    ]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={
            "_resolved_inputs": {
                "card_id": "card1",
                "item_name": "Set up basic SEO (meta tags, alt text, page titles)",
            }
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("checklist_id") == "cl_dev"
    assert r.data.get("inferred_from") == "item_name"


def test_resolve_checklist_single_checklist_without_name(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"id": "only", "name": "Solo", "checkItems": []}]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={"_resolved_inputs": {"card_id": "card1"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("checklist_id") == "only"
    assert r.data.get("inferred_from") == "single_checklist"


def test_resolve_checklist_item_name_ambiguous_two_checklists(monkeypatch: pytest.MonkeyPatch) -> None:
    dup = "Same task"
    rows = [
        {"id": "a", "name": "A", "checkItems": [{"id": "1", "name": dup}]},
        {"id": "b", "name": "B", "checkItems": [{"id": "2", "name": dup}]},
    ]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={"_resolved_inputs": {"card_id": "card1", "item_name": dup}},
    )
    r = agent.handle(msg)
    assert r.status == "clarify_user"


def test_resolve_checklist_creates_when_no_close_match(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list = [{"id": "x", "name": "Backlog"}]
    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, rows),
    )

    def post_cl(cid: str, name: str) -> tuple[int, dict]:
        return 200, {"id": "newcl", "name": name}

    monkeypatch.setattr("app.agents.trello.checklist.card_tools.post_card_checklist", post_cl)
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="resolve_checklist",
        context={"_resolved_inputs": {"card_id": "card1", "checklist_name": "Sprint 99 Goals"}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("created") is True
    assert r.data.get("checklist_id") == "newcl"


def test_set_checkitem_state_accepts_checkitem_id_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """Planner sometimes passes checkitem_id; agent must accept it (same as check_item_id)."""
    ch = [{"id": "cl1", "name": "Dev", "checkItems": [{"id": "ci99", "name": "Task", "state": "incomplete"}]}]

    monkeypatch.setattr(
        "app.agents.trello.checklist.card_tools.get_card_checklists",
        lambda cid: (200, ch),
    )
    monkeypatch.setattr(
        "app.agents.trello.checklist.cl_tools.get_checkitems",
        lambda cid: (200, ch[0]["checkItems"]),
    )
    monkeypatch.setattr(
        "app.agents.trello.checklist.cl_tools.set_checkitem_state",
        lambda card_id, ciid, state: (200, {"id": ciid, "state": state}),
    )
    agent = ChecklistAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="checklist",
        ask="set_checkitem_state",
        context={
            "_resolved_inputs": {
                "card_id": "card1",
                "checkitem_id": "ci99",
                "state": "complete",
                "skip_idempotency_check": True,
            }
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert (r.data.get("result") or {}).get("id") == "ci99"
