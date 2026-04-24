"""Build or resume Plan via OrchestratorAgent."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import plan_to_dict
from app.agents.orchestrator import OrchestratorAgent
from app.core.config import SESSION_PREFETCH
from app.governance.plan_governance import user_confirms_destructive, user_confirms_duplicate_creation
from app.session.session_prefetch import run_prefetch
from app.core.state import ChatState
from app.utils.done_intent import apply_done_intent_heuristic

logger = logging.getLogger(__name__)


def _intent_clarify_response(mem: dict[str, Any], question: str) -> dict[str, Any]:
    return {
        "plan": {},
        "skip_tools": True,
        "error_message": "",
        "needs_clarification": True,
        "clarification_question": question.strip(),
        "ambiguous_entities": {"kind": "intent_ambiguity"},
        "memory": mem,
    }


def orchestrator_node(state: ChatState) -> dict[str, Any]:
    mem: dict[str, Any] = dict(state.get("memory") or {})
    q = (state.get("question") or "").strip()
    pending = mem.get("pending_plan")

    if SESSION_PREFETCH and not mem.get("_session_prefetched"):
        mem = run_prefetch(mem)
        mem["_session_prefetched"] = True

    if isinstance(pending, dict) and pending.get("awaiting_destructive_confirm"):
        if user_confirms_destructive(q):
            plan_dict = pending.get("plan")
            if isinstance(plan_dict, dict) and plan_dict.get("plan_id"):
                pid = str(plan_dict.get("plan_id"))
                mem_out = {**mem, "pending_plan": None, "destructive_confirmed_for_plan": pid}
                return {
                    "plan": plan_dict,
                    "skip_tools": False,
                    "error_message": "",
                    "memory": mem_out,
                }
        mem_abandon = {**mem, "pending_plan": None}
        orch = OrchestratorAgent()
        analysis_d = apply_done_intent_heuristic(orch.analyze(q, mem_abandon), q)
        if analysis_d.needs_intent_clarification and (analysis_d.clarification_question or "").strip():
            return _intent_clarify_response(mem_abandon, analysis_d.clarification_question)
        try:
            plan = orch.build_plan(q, mem_abandon, analysis=analysis_d)
        except Exception as e:
            logger.exception("[orchestrator] failed after destructive cancel")
            return {
                "error_message": str(e),
                "skip_tools": True,
                "plan": {},
                "needs_clarification": False,
                "memory": mem_abandon,
            }
        return {
            "plan": plan_to_dict(plan),
            "skip_tools": False,
            "error_message": "",
            "memory": mem_abandon,
        }

    if isinstance(pending, dict) and pending.get("awaiting_duplicate_creation_confirm"):
        plan_dict_dup = pending.get("plan")
        if (
            isinstance(plan_dict_dup, dict)
            and plan_dict_dup.get("plan_id")
            and user_confirms_duplicate_creation(q)
        ):
            pid = str(plan_dict_dup.get("plan_id"))
            mem_out = {**mem, "pending_plan": None, "duplicate_creation_confirmed_for_plan": pid}
            return {
                "plan": plan_dict_dup,
                "skip_tools": False,
                "error_message": "",
                "memory": mem_out,
            }
        mem_abandon = {**mem, "pending_plan": None}
        mem_abandon.pop("duplicate_creation_confirmed_for_plan", None)
        orch = OrchestratorAgent()
        analysis_d = apply_done_intent_heuristic(orch.analyze(q, mem_abandon), q)
        if analysis_d.needs_intent_clarification and (analysis_d.clarification_question or "").strip():
            return _intent_clarify_response(mem_abandon, analysis_d.clarification_question)
        try:
            plan = orch.build_plan(q, mem_abandon, analysis=analysis_d)
        except Exception as e:
            logger.exception("[orchestrator] failed after duplicate-creation cancel")
            return {
                "error_message": str(e),
                "skip_tools": True,
                "plan": {},
                "needs_clarification": False,
                "memory": mem_abandon,
            }
        return {
            "plan": plan_to_dict(plan),
            "skip_tools": False,
            "error_message": "",
            "memory": mem_abandon,
        }

    orch = OrchestratorAgent()
    try:
        if (
            pending
            and isinstance(pending, dict)
            and pending.get("plan")
            and not pending.get("awaiting_destructive_confirm")
            and not pending.get("awaiting_duplicate_creation_confirm")
        ):
            plan = orch.resume_plan(q, pending, mem)
        else:
            analysis = apply_done_intent_heuristic(orch.analyze(q, mem), q)
            if analysis.needs_intent_clarification and (analysis.clarification_question or "").strip():
                return _intent_clarify_response(mem, analysis.clarification_question)
            plan = orch.build_plan(q, mem, analysis=analysis)
    except Exception as e:
        logger.exception("[orchestrator] failed")
        return {
            "error_message": str(e),
            "skip_tools": True,
            "plan": {},
            "needs_clarification": False,
            "memory": mem,
        }
    return {
        "plan": plan_to_dict(plan),
        "skip_tools": False,
        "error_message": "",
        "memory": mem,
    }
