"""Done intent: move to Done list vs mark due complete (dueComplete) — routing and schema."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agents.orchestrator import _Analysis
from app.utils.done_intent import apply_done_intent_heuristic, resolve_unambiguous_done_intent
from app.core.graph import route_after_orchestrator
from app.core.nodes.orchestrator_node import _intent_clarify_response, orchestrator_node


def test_resolve_unambiguous_mark_done_phrases() -> None:
    assert resolve_unambiguous_done_intent("i want to set the Ai2 to mark done") == "CARD_SET_DUE_COMPLETE"
    assert resolve_unambiguous_done_intent("set the mark the complete") == "CARD_SET_DUE_COMPLETE"
    assert resolve_unambiguous_done_intent("mark card Alpha as complete") == "CARD_SET_DUE_COMPLETE"


def test_resolve_unambiguous_move_to_done() -> None:
    assert resolve_unambiguous_done_intent("move Ai2 to Done") == "CARD_MOVE"
    assert resolve_unambiguous_done_intent("put it in the Done list") == "CARD_MOVE"


def test_resolve_set_card_to_done_means_due_complete() -> None:
    assert resolve_unambiguous_done_intent("set the card Ai to done") == "CARD_SET_DUE_COMPLETE"


def test_resolve_set_to_done_list_is_move() -> None:
    assert resolve_unambiguous_done_intent("set the card to the Done list") == "CARD_MOVE"


def test_apply_heuristic_clears_false_clarify() -> None:
    bad = _Analysis(
        needs_intent_clarification=True,
        clarification_question="Move or mark?",
        suggested_final_intent="CARD_MOVE_OR_X",
    )
    fixed = apply_done_intent_heuristic(bad, "set the Ai2 to mark done")
    assert fixed.needs_intent_clarification is False
    assert fixed.clarification_question == ""
    assert fixed.suggested_final_intent == "CARD_SET_DUE_COMPLETE"


def test_route_after_orchestrator_prefers_clarify_over_skip_tools() -> None:
    assert route_after_orchestrator({"needs_clarification": True, "skip_tools": True}) == "clarify"
    assert route_after_orchestrator({"needs_clarification": True}) == "clarify"
    assert route_after_orchestrator({"skip_tools": True}) == "reflection"
    assert route_after_orchestrator({}) == "plan_executor"


def test_analysis_model_intent_clarify_defaults() -> None:
    a = _Analysis()
    assert a.needs_intent_clarification is False
    assert a.clarification_question == ""


def test_intent_clarify_response_shape() -> None:
    mem = {"board_id": "b1"}
    out = _intent_clarify_response(mem, "Move to Done or mark due complete?")
    assert out["needs_clarification"] is True
    assert out["skip_tools"] is True
    assert out["plan"] == {}
    assert out["ambiguous_entities"]["kind"] == "intent_ambiguity"
    assert "due complete" in out["clarification_question"].lower() or "Done" in out["clarification_question"]


@patch("app.core.nodes.orchestrator_node.OrchestratorAgent")
def test_orchestrator_node_intent_clarify_short_circuits_build_plan(MockOrch: MagicMock) -> None:
    mock_orch = MockOrch.return_value
    mock_orch.analyze.return_value = _Analysis(
        user_expectation="ambiguous",
        needs_intent_clarification=True,
        clarification_question="Move to Done list or mark due complete?",
        suggested_final_intent="CARD_MOVE",
    )

    state = {
        # No "to … done" phrase — remains eligible for intent clarification when the model asks.
        "question": "set card x done",
        "memory": {
            "board_id": "b1",
            "list_map": [{"id": "l1", "name": "Done"}, {"id": "l2", "name": "Doing"}],
        },
    }
    out = orchestrator_node(state)  # type: ignore[arg-type]
    assert out["needs_clarification"] is True
    assert out["skip_tools"] is True
    assert out["plan"] == {}
    mock_orch.build_plan.assert_not_called()


@patch("app.core.nodes.orchestrator_node.OrchestratorAgent")
def test_orchestrator_node_passes_analysis_to_build_plan(MockOrch: MagicMock) -> None:
    """Single analyze() result should be reused by build_plan (no second analyze in node)."""
    mock_orch = MockOrch.return_value
    analysis = _Analysis(
        user_expectation="mark complete",
        suggested_final_intent="CARD_SET_DUE_COMPLETE",
        needs_intent_clarification=False,
    )
    mock_orch.analyze.return_value = analysis

    plan_mock = MagicMock()
    plan_mock.plan_id = "p-test"
    plan_mock.steps = []
    plan_mock.final_intent = "CARD_SET_DUE_COMPLETE"
    plan_mock.current_index = 0
    plan_mock.results = {}
    plan_mock.meta = {}

    def _to_dict(self: object) -> dict:
        return {"plan_id": "p-test", "steps": [], "final_intent": "CARD_SET_DUE_COMPLETE", "current_index": 0, "results": {}}

    with patch("app.core.nodes.orchestrator_node.plan_to_dict", return_value={"plan_id": "p-test", "steps": []}):
        mock_orch.build_plan.return_value = plan_mock
        state = {
            "question": "mark card Alpha as done",
            "memory": {"board_id": "b1", "list_map": [{"name": "Done"}]},
        }
        orchestrator_node(state)  # type: ignore[arg-type]

    mock_orch.analyze.assert_called_once()
    mock_orch.build_plan.assert_called_once()
    call_kw = mock_orch.build_plan.call_args
    assert call_kw.kwargs.get("analysis") is analysis


@patch("app.core.nodes.orchestrator_node.OrchestratorAgent")
def test_orchestrator_resume_skips_intent_clarify(MockOrch: MagicMock) -> None:
    mock_orch = MockOrch.return_value
    pending_plan = {
        "plan": {
            "plan_id": "p-old",
            "steps": [
                {
                    "step_id": "s0",
                    "agent": "card",
                    "ask": "resolve_card",
                    "inputs": {},
                    "depends_on": [],
                    "outputs": [],
                    "purpose": "",
                }
            ],
            "final_intent": "CARD_MOVE",
            "current_index": 0,
            "results": {},
            "meta": {},
        }
    }
    mock_orch.resume_plan.return_value = MagicMock(plan_id="p-old")

    with patch("app.core.nodes.orchestrator_node.plan_to_dict", return_value={"plan_id": "p-old"}):
        state = {
            "question": "the first one",
            "memory": {"pending_plan": pending_plan},
        }
        orchestrator_node(state)  # type: ignore[arg-type]

    mock_orch.analyze.assert_not_called()
    mock_orch.resume_plan.assert_called_once()
