"""OrchestratorAgent — build_plan / resume_plan via structured LLM (catalog of agents + asks only)."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.base import Plan, PlanStep, new_plan_id, plan_from_dict, plan_to_dict
from app.core.llm import get_chat_model, invoke_chat_logged
from app.prompt.orchestrator import (
    ANALYZE_SYSTEM,
    BUILD_PLAN_SYSTEM,
    RESUME_PLAN_SYSTEM,
    format_analyze_user,
    format_build_plan_user,
    format_resume_plan_user,
)
from app.session.session_memory import memory_summary_for_planner

logger = logging.getLogger(__name__)

# OpenAI structured outputs require object schemas with additionalProperties: false.
# Plain dict[str, Any] in Pydantic does not satisfy that — use JSON strings and parse locally.


def _parse_inputs_json(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        v = json.loads(str(raw).strip())
        return dict(v) if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        logger.warning("[plan] invalid inputs_json, using {}: %s", raw[:200] if raw else "")
        return {}


class _OrchestratorStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="Unique id e.g. s0, s1")
    agent: str
    ask: str
    # JSON object as a string (keys/values for this step only)
    inputs_json: str = Field(
        default="{}",
        description='Stringified JSON object, e.g. {"board_hint":"MyBoard"} or {"card_id":"$s1.card_id"}. Use {} if none.',
    )
    depends_on: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    purpose: str = ""


class _BuildPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_intent: str
    steps: list[_OrchestratorStep]


class _Analysis(BaseModel):
    """Stage-1 structured reasoning; no executable plan steps."""

    model_config = ConfigDict(extra="forbid")

    user_expectation: str = Field(
        default="",
        description="One sentence: what the user actually wants done.",
    )
    analysis: str = Field(
        default="",
        description="Short paragraph: ambiguities, implicit references, constraints, missing info.",
    )
    reasoning: str = Field(
        default="",
        description="Ordered high-level steps in natural language only; not agent.ask names or JSON.",
    )
    required_entities: list[str] = Field(
        default_factory=list,
        description="Entity types to resolve, e.g. board, list, card, member, label (lowercase tokens).",
    )
    suggested_final_intent: str = Field(
        default="",
        description="Short hint label e.g. CARD_MOVE, QUERY_BOARDS; planner may override.",
    )


class _ResumePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_continuation: bool = Field(description="True if the user is answering a pending clarification or continuing the same task")
    abandon_pending: bool = Field(default=False, description="True if the user clearly started a new unrelated task")
    target_step_id: str = ""
    patch_inputs_json: str = Field(
        default="{}",
        description='Stringified JSON object of fields to merge into the blocked step, e.g. {"list_hint":"Done"}.',
    )


class OrchestratorAgent:
    """Builds or resumes a Plan DAG; does not execute Trello calls."""

    def analyze(self, user_text: str, memory: dict[str, Any] | None) -> _Analysis:
        """Stage 1: structured reasoning only (separate LLM invoke from plan building)."""
        mem = memory or {}
        summary = memory_summary_for_planner(mem)
        try:
            llm = get_chat_model(0).with_structured_output(_Analysis)
            prompt = format_analyze_user(memory_summary=summary, user_text=user_text)
            raw = invoke_chat_logged(
                llm,
                [{"role": "system", "content": ANALYZE_SYSTEM}, {"role": "user", "content": prompt}],
                operation="orchestrator_analyze",
            )
            out = raw if isinstance(raw, _Analysis) else _Analysis.model_validate(raw)
            logger.info(
                "[plan] analyze intent=%s required=%s",
                out.suggested_final_intent,
                out.required_entities,
            )
            return out
        except Exception:
            logger.warning("[plan] analyze failed; continuing without analyzer output", exc_info=True)
            return _Analysis()

    def build_plan(self, user_text: str, memory: dict[str, Any] | None) -> Plan:
        mem = memory or {}
        analysis = self.analyze(user_text, mem)
        analysis_dict = analysis.model_dump()
        meta_base: dict[str, Any] = {"user_text": user_text, "analysis": analysis_dict}

        llm = get_chat_model(0).with_structured_output(_BuildPlan)
        summary = memory_summary_for_planner(mem)
        prompt = format_build_plan_user(memory_summary=summary, user_text=user_text, analysis=analysis_dict)
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": BUILD_PLAN_SYSTEM}, {"role": "user", "content": prompt}],
            operation="orchestrator_build_plan",
        )
        out = raw if isinstance(raw, _BuildPlan) else _BuildPlan.model_validate(raw)
        if not out.steps:
            logger.warning("[plan] LLM returned no steps; using fallback resolve_board → get_board_cards")
            pid = new_plan_id()
            return Plan(
                plan_id=pid,
                steps=[
                    PlanStep(
                        step_id="s0",
                        agent="board",
                        ask="resolve_board",
                        inputs={},
                        depends_on=[],
                        outputs=["board_id"],
                        purpose="fallback board",
                    ),
                    PlanStep(
                        step_id="s1",
                        agent="board",
                        ask="get_board_cards",
                        inputs={"board_id": "$s0.board_id"},
                        depends_on=["s0"],
                        outputs=["cards"],
                        purpose="fallback list cards",
                    ),
                ],
                final_intent=out.final_intent or "get_board_cards",
                current_index=0,
                results={},
                meta=dict(meta_base),
            )
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
            for s in out.steps
        ]
        plan = Plan(plan_id=pid, steps=steps, final_intent=out.final_intent, current_index=0, results={}, meta=dict(meta_base))
        logger.info(
            "[plan] built plan_id=%s steps=[%s]",
            pid,
            ", ".join(f"{x.agent}.{x.ask}" for x in steps),
        )
        return plan

    def resume_plan(self, user_text: str, pending: dict[str, Any], memory: dict[str, Any] | None) -> Plan:
        """Patch blocked plan from user follow-up."""
        mem = memory or {}
        plan = plan_from_dict(pending.get("plan") or pending)
        llm = get_chat_model(0).with_structured_output(_ResumePlan)
        summary = memory_summary_for_planner(mem)
        idx = int(plan.current_index)
        cur = plan.steps[idx] if 0 <= idx < len(plan.steps) else None
        prompt = format_resume_plan_user(
            memory_summary=summary,
            user_text=user_text,
            plan_dict=plan_to_dict(plan),
            blocked_step_id=cur.step_id if cur else "none",
            blocked_ask=cur.ask if cur else "",
        )
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": RESUME_PLAN_SYSTEM}, {"role": "user", "content": prompt}],
            operation="orchestrator_resume_plan",
        )
        out = raw if isinstance(raw, _ResumePlan) else _ResumePlan.model_validate(raw)
        if out.abandon_pending or not out.is_continuation:
            logger.info("[plan] resume abandoned — building fresh plan")
            return self.build_plan(user_text, mem)

        tid = out.target_step_id or (cur.step_id if cur else "")
        patch = _parse_inputs_json(out.patch_inputs_json)
        if tid and patch:
            for i, st in enumerate(plan.steps):
                if st.step_id == tid:
                    merged = dict(st.inputs)
                    merged.update(patch)
                    plan.steps[i] = PlanStep(
                        step_id=st.step_id,
                        agent=st.agent,
                        ask=st.ask,
                        inputs=merged,
                        depends_on=st.depends_on,
                        outputs=st.outputs,
                        purpose=st.purpose,
                    )
                    break
        plan.meta["user_text"] = user_text
        logger.info("[plan] resume from step=%s plan_id=%s user_text=%s", plan.current_index, plan.plan_id, user_text[:120])
        return plan


def pending_plan_blob(plan: Plan) -> dict[str, Any]:
    return {"plan": plan_to_dict(plan), "version": 1}
