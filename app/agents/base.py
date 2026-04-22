"""A2A message contracts, Plan DAG, and BaseAgent (LLM via invoke_chat_logged)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.llm import get_chat_model, invoke_chat_logged

Status = Literal["ok", "need_info", "clarify_user", "error"]


@dataclass
class A2AMessage:
    task_id: str
    frm: str
    to: str
    ask: str
    context: dict[str, Any]
    expects: list[str] = field(default_factory=list)


@dataclass
class A2AResponse:
    task_id: str
    frm: str
    status: Status
    data: dict[str, Any]
    missing: list[str] = field(default_factory=list)
    clarification: str | None = None
    error: str | None = None


@dataclass
class PlanStep:
    step_id: str
    agent: str
    ask: str
    inputs: dict[str, Any]
    depends_on: list[str]
    outputs: list[str]
    purpose: str = ""


@dataclass
class Plan:
    plan_id: str
    steps: list[PlanStep]
    final_intent: str
    current_index: int = 0
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def new_plan_id() -> str:
    return f"p-{uuid.uuid4().hex[:12]}"


def new_task_id() -> str:
    return f"t-{uuid.uuid4().hex[:10]}"


_REF_RE = re.compile(r"^\$([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)$")


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_REF_RE.match(value))


def parse_ref(value: str) -> tuple[str, str] | None:
    m = _REF_RE.match(value.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def plan_to_dict(p: Plan) -> dict[str, Any]:
    return {
        "plan_id": p.plan_id,
        "final_intent": p.final_intent,
        "current_index": p.current_index,
        "steps": [step_to_dict(s) for s in p.steps],
        "results": dict(p.results),
        "meta": dict(p.meta),
    }


def plan_from_dict(d: dict[str, Any]) -> Plan:
    steps_raw = d.get("steps") or []
    steps = [step_from_dict(x) for x in steps_raw if isinstance(x, dict)]
    return Plan(
        plan_id=str(d.get("plan_id") or new_plan_id()),
        final_intent=str(d.get("final_intent") or "unknown"),
        current_index=int(d.get("current_index") or 0),
        steps=steps,
        results=dict(d.get("results") or {}) if isinstance(d.get("results"), dict) else {},
        meta=dict(d.get("meta") or {}) if isinstance(d.get("meta"), dict) else {},
    )


def step_to_dict(s: PlanStep) -> dict[str, Any]:
    return {
        "step_id": s.step_id,
        "agent": s.agent,
        "ask": s.ask,
        "inputs": dict(s.inputs),
        "depends_on": list(s.depends_on),
        "outputs": list(s.outputs),
        "purpose": s.purpose,
    }


def step_from_dict(d: dict[str, Any]) -> PlanStep:
    return PlanStep(
        step_id=str(d.get("step_id") or "s0"),
        agent=str(d.get("agent") or ""),
        ask=str(d.get("ask") or ""),
        inputs=dict(d.get("inputs") or {}),
        depends_on=[str(x) for x in (d.get("depends_on") or [])],
        outputs=[str(x) for x in (d.get("outputs") or [])],
        purpose=str(d.get("purpose") or ""),
    )


class BaseAgent:
    """Specialist agent: subclass implements _handle for each `ask`."""

    name: str = "base"

    def __init__(self) -> None:
        self.bus: Any = None  # set by AgentBus.register

    def handle(self, msg: A2AMessage) -> A2AResponse:
        raise NotImplementedError

    def llm(self, temperature: float = 0.0):
        return get_chat_model(temperature)

    def invoke_llm(self, messages: list[Any], *, operation: str) -> Any:
        return invoke_chat_logged(self.llm(), messages, operation=operation)
