"""get_member_cards with board_id filters to cards on that board only."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.trello.member import MemberAgent


def test_get_member_cards_filters_by_board_id(monkeypatch: pytest.MonkeyPatch) -> None:
    board_a = "board111"
    board_b = "board222"
    api_cards = [
        {"id": "c1", "name": "On A", "idBoard": board_a},
        {"id": "c2", "name": "On B", "idBoard": board_b},
        {"id": "c3", "name": "Also A", "idBoard": board_a},
    ]

    def fake_get_member_cards(mid: str, **params: object) -> tuple[int, list]:
        assert mid == "mem99"
        assert "idBoard" in (params.get("fields") or "")
        return 200, list(api_cards)

    monkeypatch.setattr("app.agents.trello.member.member_tools.get_member_cards", fake_get_member_cards)
    agent = MemberAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="member",
        ask="get_member_cards",
        context={
            "_resolved_inputs": {
                "member_id": "mem99",
                "board_id": board_a,
            }
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    ids = {c.get("id") for c in (r.data.get("cards") or [])}
    assert ids == {"c1", "c3"}
    assert r.data.get("board_id") == board_a


def test_get_member_cards_without_board_id_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    api_cards = [{"id": "x1", "name": "Any"}]

    def fake_get_member_cards(mid: str, **params: object) -> tuple[int, list]:
        assert mid == "me"
        assert "fields" not in params
        return 200, list(api_cards)

    monkeypatch.setattr("app.agents.trello.member.member_tools.get_member_cards", fake_get_member_cards)
    agent = MemberAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="member",
        ask="get_member_cards",
        context={"_resolved_inputs": {}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert len(r.data.get("cards") or []) == 1
    assert "board_id" not in r.data
