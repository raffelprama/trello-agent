"""Clarification — pending plan persistence is handled in clarify node + session_memory.finalize_turn_memory."""

from __future__ import annotations

from typing import Any


def merge_pending_plan(memory: dict[str, Any], payload: dict[str, Any] | None) -> dict[str, Any]:
    m = dict(memory or {})
    if isinstance(payload, dict) and payload.get("plan"):
        m["pending_plan"] = payload
    return m
