"""Resolution helpers (PRD §5.1 tiers)."""

from app.resolution import best_match_by_name, levenshtein, match_dicts_by_name


def test_levenshtein() -> None:
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("a", "a") == 0


def test_match_dicts_exact_prefix_substring() -> None:
    boards = [{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}]
    assert match_dicts_by_name("Alpha", boards) == boards[0]
    assert match_dicts_by_name("Alp", boards) == boards[0]
    assert match_dicts_by_name("ph", boards) == boards[0]


def test_match_dicts_levenshtein_single() -> None:
    boards = [{"id": "1", "name": "Planning"}, {"id": "2", "name": "Other"}]
    # "Planing" one char off
    assert match_dicts_by_name("Planing", boards) == boards[0]


def test_best_match_typed() -> None:
    rows = ["foo", "foobar"]
    assert best_match_by_name("foo", rows, get_name=lambda x: x) == "foo"
