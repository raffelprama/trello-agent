"""BulkOrchestratorNode — builds a foreach/batch Plan for bulk tasks."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import Plan, PlanStep, new_plan_id, plan_to_dict
from app.agents.orchestrator import _BuildPlan, _parse_inputs_json
from app.core.llm import get_chat_model, invoke_chat_logged
from app.core.state import ChatState
from app.prompt.bulk_orchestrator import BULK_BUILD_PLAN_SYSTEM, format_bulk_build_plan_user
from app.session.session_memory import memory_summary_for_planner

logger = logging.getLogger(__name__)


def bulk_orchestrator_node(state: ChatState) -> dict[str, Any]:
    mem: dict[str, Any] = dict(state.get("memory") or {})
    q = (state.get("question") or "").strip()

    summary = memory_summary_for_planner(mem)
    try:
        llm = get_chat_model(0).with_structured_output(_BuildPlan)
        prompt = format_bulk_build_plan_user(memory_summary=summary, user_text=q)
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": BULK_BUILD_PLAN_SYSTEM}, {"role": "user", "content": prompt}],
            operation="bulk_orchestrator_build_plan",
        )
        out = raw if isinstance(raw, _BuildPlan) else _BuildPlan.model_validate(raw)
    except Exception as e:
        logger.exception("[bulk_orchestrator] failed")
        return {
            "error_message": str(e),
            "skip_tools": True,
            "plan": {},
            "needs_clarification": False,
            "memory": mem,
        }

    pid = new_plan_id()
    steps = [
        PlanStep(
            step_id=s.step_id,
            agent=s.agent,
            ask=s.ask,
            inputs=_parse_inputs_json(s.inputs_json),
            depends_on=list(s.depends_on),
            outputs=list(s.outputs),
            purpose=s.purpose or "",
        )
        for s in (out.steps or [])
    ]
    plan = Plan(
        plan_id=pid,
        steps=steps,
        final_intent=out.final_intent or "BULK_ACTION",
        current_index=0,
        results={},
        meta={"user_text": q},
    )
    logger.info(
        "[bulk_orchestrator] built plan_id=%s steps=[%s]",
        pid,
        ", ".join(f"{x.agent}.{x.ask}" for x in steps),
    )
    return {
        "plan": plan_to_dict(plan),
        "skip_tools": False,
        "error_message": "",
        "memory": mem,
    }
