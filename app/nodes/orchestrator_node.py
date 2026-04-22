"""Build or resume Plan via OrchestratorAgent."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.base import plan_to_dict
from app.agents.orchestrator import OrchestratorAgent
from app.state import ChatState

logger = logging.getLogger(__name__)


def orchestrator_node(state: ChatState) -> dict[str, Any]:
    mem = state.get("memory") or {}
    q = (state.get("question") or "").strip()
    pending = mem.get("pending_plan")
    orch = OrchestratorAgent()
    try:
        if pending and isinstance(pending, dict):
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
        }
    return {
        "plan": plan_to_dict(plan),
        "skip_tools": False,
        "error_message": "",
    }
