"""resolve_board accepts board_id alone (no hint) — avoids re-listing all boards."""

from __future__ import annotations

import pytest

from app.agents.base import A2AMessage, new_task_id
from app.agents.trello.board import BoardAgent


def test_resolve_board_ok_with_board_id_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_board(bid: str) -> tuple[int, dict]:
        return 200, {"id": bid, "name": "HRGA"}

    monkeypatch.setattr("app.agents.trello.board.board_tools.get_board", get_board)
    calls: list[str] = []

    def get_my_boards() -> tuple[int, list]:
        calls.append("list")
        return 200, []

    monkeypatch.setattr("app.agents.trello.board.member_tools.get_my_boards", get_my_boards)
    monkeypatch.setattr("app.agents.trello.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.trello.board.TRELLO_BOARD_ID", "")

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

    monkeypatch.setattr("app.agents.trello.board.member_tools.get_my_boards", lambda: (200, boards))
    monkeypatch.setattr("app.agents.trello.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.trello.board.TRELLO_BOARD_ID", "")

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


def test_resolve_board_list_intent_returns_boards_not_clarify(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phrases like 'what boards are available' must not treat 'that available' as a board name."""
    boards = [
        {"id": "a", "name": "AXA Agency", "closed": True, "shortUrl": "https://trello.com/b/a"},
        {"id": "b", "name": "HRGA", "closed": False, "shortUrl": "https://trello.com/b/b"},
    ]
    monkeypatch.setattr("app.agents.trello.board.member_tools.get_my_boards", lambda: (200, boards))
    monkeypatch.setattr("app.agents.trello.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.trello.board.TRELLO_BOARD_ID", "")

    agent = BoardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="board",
        ask="resolve_board",
        context={
            "_resolved_inputs": {},
            "memory": {},
            "user_text": "what are board that available",
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("board_count") == 2
    names = [x.get("name") for x in (r.data.get("boards") or [])]
    assert "HRGA" in names and "AXA Agency" in names


def test_resolve_board_lists_on_named_board_not_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """'see all lists under board Test' must resolve board Test, not return all boards."""
    boards = [
        {"id": "69688f0f940d3f5c7e2062ca", "name": "Test", "closed": False, "shortUrl": "https://x/t"},
        {"id": "other", "name": "HRGA", "closed": False, "shortUrl": "https://x/h"},
    ]
    monkeypatch.setattr("app.agents.trello.board.member_tools.get_my_boards", lambda: (200, boards))
    monkeypatch.setattr("app.agents.trello.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.trello.board.TRELLO_BOARD_ID", "")

    agent = BoardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="board",
        ask="resolve_board",
        context={
            "_resolved_inputs": {"board_hint": ""},
            "memory": {},
            "user_text": "i want to see all lists under board 'Test'",
        },
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert r.data.get("board_id") == "69688f0f940d3f5c7e2062ca"
    assert r.data.get("resolved_board_name") == "Test"
    assert r.data.get("board_count") is None


@pytest.mark.parametrize(
    "user_phrase",
    [
        "i want to see all the board",
        "list me all the board",
        "show me all the boards",
    ],
)
def test_resolve_board_catalog_singular_board_phrasing(
    monkeypatch: pytest.MonkeyPatch, user_phrase: str
) -> None:
    boards = [{"id": "b1", "name": "Alpha", "closed": False, "shortUrl": "https://x/1"}]
    monkeypatch.setattr("app.agents.trello.board.member_tools.get_my_boards", lambda: (200, boards))
    monkeypatch.setattr("app.agents.trello.board.BOARD_SCOPE_ONLY", False)
    monkeypatch.setattr("app.agents.trello.board.TRELLO_BOARD_ID", "")

    agent = BoardAgent()
    msg = A2AMessage(
        task_id=new_task_id(),
        frm="test",
        to="board",
        ask="resolve_board",
        context={"_resolved_inputs": {}, "memory": {}, "user_text": user_phrase},
    )
    r = agent.handle(msg)
    assert r.status == "ok"
    assert (r.data.get("boards") or [{}])[0].get("name") == "Alpha"
