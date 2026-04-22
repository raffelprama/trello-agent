"""resolve_board accepts board_id alone (no hint) — avoids re-listing all boards."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.board import BoardAgent


def test_resolve_board_ok_with_board_id_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_board(bid: str) -> tuple[int, dict]:
        return 200, {"id": bid, "name": "HRGA"}

    monkeypatch.setattr("app.agents.board.board_tools.get_board", get_board)
    calls: list[str] = []

    def get_my_boards() -> tuple[int, list]:
        calls.append("list")
        return 200, []

    monkeypatch.setattr("app.agents.board.member_tools.get_my_boards", get_my_boards)
    monkeypatch.setattr("app.agents.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.board.TRELLO_BOARD_ID", "")

    agent = BoardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="board",
        ask="resolve_board",
        context={"_resolved_inputs": {"board_id": "b-hrga", "board_hint": ""}, "memory": {}},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("board_id") == "b-hrga"
    assert r.data.get("resolved_board_name") == "HRGA"
    assert calls == []


def test_resolve_board_hint_still_wins_over_stale_board_id(monkeypatch: pytest.MonkeyPatch) -> None:
    boards = [
        {"id": "correct", "name": "HRGA"},
        {"id": "wrong", "name": "Test"},
    ]

    monkeypatch.setattr("app.agents.board.member_tools.get_my_boards", lambda: (200, boards))
    monkeypatch.setattr("app.agents.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.board.TRELLO_BOARD_ID", "")

    agent = BoardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="board",
        ask="resolve_board",
        context={
            "_resolved_inputs": {"board_id": "wrong", "board_hint": "HRGA"},
            "memory": {},
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("board_id") == "correct"
