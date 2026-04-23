"""Card name hint matching — avoid substring false positives (e.g. 'Ai' vs 'TEST_AGAIN')."""

from __future__ import annotations

from app.agents.trello.card import _card_name_matches_hint


def test_hint_ai_does_not_match_test_again() -> None:
    assert not _card_name_matches_hint("Ai", "TEST_AGAIN")
    assert not _card_name_matches_hint("Ai", "TEST_AGAIN3")
    assert _card_name_matches_hint("Ai", "Ai")
    assert _card_name_matches_hint("Ai", "Ai2")


def test_prefix_and_token_boundaries() -> None:
    assert _card_name_matches_hint("Hero", "Hero")
    assert _card_name_matches_hint("test", "TEST_AGAIN")
    assert _card_name_matches_hint("again", "TEST_AGAIN")
