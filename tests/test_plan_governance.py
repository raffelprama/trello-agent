"""Plan governance flags."""

from app.agents.base import Plan, PlanStep, new_plan_id
from app.plan_governance import (
    is_destructive,
    is_mutating,
    plan_has_destructive,
    user_confirms_destructive,
)


def test_mutating_and_destructive() -> None:
    assert is_mutating("card", "move_card")
    assert not is_mutating("board", "get_board")
    assert is_destructive("card", "delete_card")
    assert not is_destructive("card", "move_card")


def test_new_mutating_card_and_checklist_steps() -> None:
    assert is_mutating("card", "set_card_due")
    assert is_mutating("card", "set_card_due_complete")
    assert is_mutating("card", "add_card_member")
    assert is_mutating("checklist", "create_checklist")
    assert not is_mutating("member", "resolve_member")


def test_user_confirms() -> None:
    assert user_confirms_destructive("yes")
    assert user_confirms_destructive("OK")
    assert not user_confirms_destructive("maybe")


def test_plan_has_destructive() -> None:
    p = Plan(
        plan_id=new_plan_id(),
        steps=[
            PlanStep("s0", "board", "resolve_board", {}, [], [], ""),
            PlanStep("s1", "card", "delete_card", {}, ["s0"], [], ""),
        ],
        final_intent="CARD_DELETE",
    )
    assert plan_has_destructive(p.steps)
    p2 = Plan(
        plan_id=new_plan_id(),
        steps=[PlanStep("s0", "board", "get_board", {}, [], [], "")],
        final_intent="x",
    )
    assert not plan_has_destructive(p2.steps)
