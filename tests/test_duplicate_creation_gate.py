"""Duplicate-creation preflight helpers in plan_executor."""

from __future__ import annotations

from unittest.mock import patch

from app.agents.base import Plan, PlanStep, new_plan_id
from app.core.nodes.plan_executor import (
    _creation_pair_conflict,
    _duplicate_creation_conflicts,
    _topic_conflicts_scaffold,
)


def test_creation_pair_conflict() -> None:
    assert _creation_pair_conflict("task1", "task1")
    assert _creation_pair_conflict("Task1", "task1")
    assert _creation_pair_conflict("Hero", "hero")
    assert not _creation_pair_conflict("abc", "xyz")


def test_topic_conflicts_scaffold() -> None:
    assert _topic_conflicts_scaffold("marketing campaign", "Marketing campaign brief")
    assert not _topic_conflicts_scaffold("unrelated topic xyz", "totally different card")


def test_duplicate_creation_conflicts_batch() -> None:
    plan = Plan(
        plan_id=new_plan_id(),
        steps=[
            PlanStep("s0", "board", "resolve_board", {"board_hint": "X"}, [], [], ""),
            PlanStep("s1", "batch", "create_cards", {"list_id": "L1", "names": ["task1", "task2"]}, ["s0"], [], ""),
        ],
        final_intent="BULK",
        results={"s0": {"board_id": "B1"}},
    )
    mem = {"board_id": "B1"}
    resolved = {"list_id": "L1", "names": ["task1", "newbie"]}
    step = plan.steps[1]
    with patch("app.core.nodes.plan_executor.list_tools.get_list_cards") as glc:
        glc.return_value = (
            200,
            [{"id": "c1", "name": "task1"}, {"id": "c2", "name": "something else"}],
        )
        conf = _duplicate_creation_conflicts(step, resolved, plan, mem)
    assert any(c.get("planned") == "task1" and c.get("existing") == "task1" for c in conf)
    assert not any(c.get("planned") == "newbie" for c in conf)
