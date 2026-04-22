"""Deprecated: single planner replaced by OrchestratorAgent + plan_executor."""

from __future__ import annotations

from app.nodes.orchestrator_node import orchestrator_node as normalize_intent_planner

__all__ = ["normalize_intent_planner"]
