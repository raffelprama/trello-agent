"""Trello payload slimming for LLM context."""

from __future__ import annotations

from app.utils.trello_summaries import slim_board, slim_boards, slim_result_for_answer


def test_slim_board_drops_heavy_fields() -> None:
    fat = {
        "id": "x",
        "name": "HRGA",
        "closed": False,
        "limits": {"cards": {"openPerBoard": {"status": "ok"}}},
        "prefs": {"permissionLevel": "org"},
        "labelNames": {"green": "Done"},
        "memberships": [{"idMember": "m1"}],
    }
    s = slim_board(fat)
    assert s == {
        "id": "x",
        "name": "HRGA",
        "closed": False,
        "url": None,
        "starred": None,
        "dateLastActivity": None,
    }


def test_slim_result_for_answer_boards_and_board() -> None:
    data = {
        "boards": [{"id": "1", "name": "A", "limits": {}}],
        "board": {"id": "2", "name": "B", "prefs": {}},
    }
    slim = slim_result_for_answer(data)
    assert slim["boards"] == [
        {"id": "1", "name": "A", "closed": None, "url": None, "starred": None, "dateLastActivity": None},
    ]
    assert slim["board"]["name"] == "B"
    assert "prefs" not in slim["board"]


def test_slim_boards_skips_non_dicts() -> None:
    assert slim_boards([{"id": "1", "name": "Z"}, None, "x"]) == [
        {"id": "1", "name": "Z", "closed": None, "url": None, "starred": None, "dateLastActivity": None},
    ]
