"""close_name_matches — fuzzy board disambiguation."""

from __future__ import annotations

from app.utils.resolution import close_name_matches, match_dicts_by_name


def test_close_name_matches_finds_typos() -> None:
    boards = [
        {"id": "1", "name": "Test"},
        {"id": "2", "name": "Production"},
        {"id": "3", "name": "HRGA"},
    ]
    # Primary matcher already resolves unique Levenshtein ≤2 ("tst" → "Test").
    assert match_dicts_by_name("tst", boards) == boards[0]
    close = close_name_matches("tst", boards, get_name=lambda b: str(b.get("name", "")), max_levenshtein=2)
    assert len(close) >= 1
    assert close[0].get("name") == "Test"


def test_close_name_matches_when_primary_has_no_unique_fuzzy() -> None:
    """Multiple rows within Levenshtein band → best_match None; close_name_matches lists both."""
    boards = [{"id": "1", "name": "Cat"}, {"id": "2", "name": "Cut"}]
    assert match_dicts_by_name("cot", boards) is None
    close = close_name_matches("cot", boards, get_name=lambda b: str(b.get("name", "")), max_levenshtein=2)
    names = {b.get("name") for b in close}
    assert names == {"Cat", "Cut"}


def test_close_name_matches_respects_max_results() -> None:
    rows = [{"id": str(i), "name": f"Board{i}"} for i in range(10)]
    close = close_name_matches("board0", rows, get_name=lambda b: str(b.get("name", "")), max_levenshtein=3, max_results=3)
    assert len(close) <= 3
