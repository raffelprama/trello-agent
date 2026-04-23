"""Build or resume Plan via OrchestratorAgent."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import plan_to_dict
from app.agents.orchestrator import OrchestratorAgent
from app.core.config import SESSION_PREFETCH
from app.governance.plan_governance import user_confirms_destructive
from app.session.session_prefetch import run_prefetch
from app.core.state import ChatState

logger = logging.getLogger(__name__)


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
        try:
            plan = orch.build_plan(q, mem_abandon)
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

    orch = OrchestratorAgent()
    try:
        if pending and isinstance(pending, dict) and pending.get("plan") and not pending.get("awaiting_destructive_confirm"):
            plan = orch.resume_plan(q, pending, mem)
        else:
            plan = orch.build_plan(q, mem)
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
