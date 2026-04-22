"""Execute Plan DAG via AgentBus — resolves $step.field refs, handles need_info / clarify / error."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agents.base import A2AMessage, Plan, PlanStep, new_task_id, parse_ref, plan_to_dict
from app.agents.bus import get_default_bus
from app.intent_taxonomy import normalize_intent_label
from app.plan_governance import effective_confirm_mutations, effective_dry_run, is_destructive, is_mutating
from app.state import ChatState
from app.trello_client import get_client

logger = logging.getLogger(__name__)

_MAX_INSERT = 8


def _resolve_value(val: Any, results: dict[str, dict[str, Any]]) -> Any:
    if not isinstance(val, str):
        return val
    v = val.strip()
    pr = parse_ref(v)
    if pr:
        sid, field = pr
        return (results.get(sid) or {}).get(field)
    return val


def _resolve_inputs(inputs: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (inputs or {}).items():
        out[k] = _resolve_value(v, results)
    return out


def _merge_memory_into_inputs(
    missing: list[str],
    mem: dict[str, Any],
    cur: dict[str, Any],
    *,
    results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    m = dict(cur)
    keymap = {
        "board_id": "board_id",
        "list_id": "list_id",
        "card_id": "card_id",
        "target_list_id": "target_list_id",
    }

    def _latest_result_field(field: str) -> Any:
        if not results:
            return None
        for _sid, data in reversed(list(results.items())):
            if isinstance(data, dict) and data.get(field):
                return data[field]
        return None

    for miss in missing:
        mk = keymap.get(miss)
        if not mk or m.get(mk):
            continue
        if mem.get(mk):
            m[mk] = mem[mk]
        else:
            lr = _latest_result_field(mk)
            if lr:
                m[mk] = lr
    return m


def _auto_step_for_missing(missing: str, plan: Plan, user_text: str) -> PlanStep | None:
    uid = uuid.uuid4().hex[:6]
    if missing == "board_id":
        return PlanStep(
            step_id=f"_auto_{uid}",
            agent="board",
            ask="resolve_board",
            inputs={"board_hint": ""},
            depends_on=[],
            outputs=["board_id"],
            purpose="auto-resolve board",
        )
    if missing == "list_id":
        return PlanStep(
            step_id=f"_auto_{uid}",
            agent="list",
            ask="resolve_list",
            inputs={"list_hint": "", "board_id": "$PREV.board_id"},
            depends_on=[],
            outputs=["list_id"],
            purpose="auto-resolve list",
        )
    if missing == "card_id":
        return PlanStep(
            step_id=f"_auto_{uid}",
            agent="card",
            ask="resolve_card",
            inputs={"card_hint": "", "board_id": "$PREV.board_id"},
            depends_on=[],
            outputs=["card_id"],
            purpose="auto-resolve card",
        )
    return None


def _substitute_prev_refs(step: PlanStep, board_field: str | None) -> PlanStep:
    """Replace $PREV.board_id with last known board_id in inputs (handled at dispatch via results)."""
    if not board_field:
        return step
    ins = dict(step.inputs)
    for k, v in list(ins.items()):
        if isinstance(v, str) and v.startswith("$PREV"):
            ins[k] = board_field
    return PlanStep(
        step_id=step.step_id,
        agent=step.agent,
        ask=step.ask,
        inputs=ins,
        depends_on=step.depends_on,
        outputs=step.outputs,
        purpose=step.purpose,
    )


def _deps_satisfied(step: PlanStep, results: dict[str, dict[str, Any]]) -> bool:
    for d in step.depends_on:
        if d not in results:
            return False
    return True


def _aggregate_parsed(plan: Plan, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Shape tool-like parsed_response for AnswerAgent + memory extraction."""
    out: dict[str, Any] = {"plan_id": plan.plan_id, "final_intent": plan.final_intent, "step_summaries": {}}
    for sid, data in results.items():
        if sid.startswith("_auto_"):
            continue
        out["step_summaries"][sid] = {k: data[k] for k in list(data.keys())[:24]}
        if "queried_board" in data:
            out["queried_board"] = data["queried_board"]
        if "cards" in data:
            out["cards"] = data["cards"]
        if "card" in data:
            out["card"] = data["card"]
        if "lists" in data:
            out["lists"] = data["lists"]
        if "labels" in data:
            out["labels"] = data["labels"]
        if "member" in data:
            out["member"] = data["member"]
        if "boards" in data:
            out["boards"] = data["boards"]
        if "checklists" in data:
            out["checklists"] = data["checklists"]
        if "comments" in data:
            out["comments"] = data["comments"]
        if "custom_fields" in data:
            out["custom_fields"] = data["custom_fields"]
        if "webhooks" in data:
            out["webhooks"] = data["webhooks"]
        if isinstance(data.get("board"), dict):
            b = data["board"]
            out["queried_board"] = {"id": b.get("id"), "name": b.get("name")}
    return out


def _destructive_confirm_question(step: PlanStep) -> str:
    return (
        f"This step is destructive: {step.agent}.{step.ask}. "
        "Reply with yes to proceed, or rephrase to cancel."
    )


def plan_executor_node(state: ChatState) -> dict[str, Any]:
    plan_dict = state.get("plan")
    if not isinstance(plan_dict, dict):
        return {
            "error_message": "No plan to execute",
            "plan_execution_status": "error",
            "skip_tools": True,
            "http_status": 400,
        }

    from app.agents.base import plan_from_dict

    plan = plan_from_dict(plan_dict)
    if not plan.steps:
        return {
            "error_message": "Empty plan (nothing to execute)",
            "plan_execution_status": "error",
            "http_status": 400,
        }
    mem = state.get("memory") or {}
    question = state.get("question") or ""
    bus = get_default_bus()

    user_text = str(plan.meta.get("user_text") or question)
    inserts = 0
    all_trace: list[dict[str, Any]] = []

    # Resolve $PREV.board_id using latest board_id from results or memory
    def latest_board_id() -> str | None:
        for _sid, data in reversed(list(plan.results.items())):
            if isinstance(data, dict) and data.get("board_id"):
                return str(data["board_id"])
        x = mem.get("board_id")
        return str(x) if x else None

    while plan.current_index < len(plan.steps):
        step = plan.steps[plan.current_index]
        if not _deps_satisfied(step, plan.results):
            return {
                "error_message": f"Unsatisfied dependencies for step {step.step_id}",
                "plan_execution_status": "error",
                "http_status": 400,
                "plan": plan_to_dict(plan),
            }

        lb = latest_board_id()
        if lb and "$PREV.board_id" in str(step.inputs):
            step = _substitute_prev_refs(step, lb)
            plan.steps[plan.current_index] = step

        resolved = _resolve_inputs(step.inputs, plan.results)
        # Inject board_id from memory if still missing for list/card
        if not resolved.get("board_id") and mem.get("board_id"):
            hint_for_board = str(resolved.get("board_hint") or resolved.get("name") or "").strip()
            if not (step.agent == "board" and step.ask == "resolve_board" and hint_for_board):
                resolved["board_id"] = mem.get("board_id")

        ctx: dict[str, Any] = {
            "user_text": user_text,
            "memory": mem,
            "_resolved_inputs": resolved,
        }

        if is_destructive(step.agent, step.ask) and effective_confirm_mutations(mem):
            if str(mem.get("destructive_confirmed_for_plan") or "") != str(plan.plan_id):
                q = _destructive_confirm_question(step)
                return {
                    "plan": plan_to_dict(plan),
                    "plan_trace": all_trace,
                    "needs_clarification": True,
                    "clarification_question": q,
                    "ambiguous_entities": {"kind": "destructive_confirm", "step": f"{step.agent}.{step.ask}"},
                    "plan_execution_status": "clarify",
                    "pending_plan_payload": {"plan": plan_to_dict(plan), "awaiting_destructive_confirm": True},
                    "http_status": 200,
                    "parsed_response": {"clarification": True, "question": q},
                }

        dry = effective_dry_run(mem if isinstance(mem, dict) else None)
        if dry and is_mutating(step.agent, step.ask):
            trace_dr = {
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "agent": step.agent,
                "ask": step.ask,
                "status": "dry_run_skipped",
                "dry_run_skipped": True,
            }
            all_trace.append(trace_dr)
            parsed = _aggregate_parsed(plan, plan.results)
            parsed["dry_run"] = True
            parsed["dry_run_stopped_at"] = step.step_id
            return {
                "plan": plan_to_dict(plan),
                "plan_trace": all_trace,
                "parsed_response": parsed,
                "plan_execution_status": "ok",
                "http_status": 200,
                "error_message": "",
                "entities": _entities_from_results(plan.results),
                "intent": normalize_intent_label(plan.final_intent),
                "selected_tool": "a2a_plan",
            }

        msg = A2AMessage(
            task_id=new_task_id(),
            frm="executor",
            to=step.agent,
            ask=step.ask,
            context=ctx,
        )
        logger.info(
            "[plan] exec plan_id=%s step=%s agent=%s ask=%s",
            plan.plan_id,
            step.step_id,
            step.agent,
            step.ask,
        )
        resp = bus.dispatch(msg)
        trace: dict[str, Any] = {
            "plan_id": plan.plan_id,
            "step_id": step.step_id,
            "agent": step.agent,
            "ask": step.ask,
            "status": resp.status,
        }
        http_rec = get_client().consume_http_trace()
        if http_rec:
            trace["http"] = http_rec
        all_trace.append(trace)

        if resp.status == "ok":
            plan.results[step.step_id] = dict(resp.data or {})
            plan.current_index += 1
            continue

        if resp.status == "need_info":
            merged = _merge_memory_into_inputs(resp.missing or [], mem, resolved, results=plan.results)
            if merged != resolved:
                ctx2 = {**ctx, "_resolved_inputs": merged}
                msg2 = A2AMessage(task_id=new_task_id(), frm="executor", to=step.agent, ask=step.ask, context=ctx2)
                resp2 = bus.dispatch(msg2)
                tr2 = {**trace, "status": resp2.status, "retry": True}
                h2 = get_client().consume_http_trace()
                if h2:
                    tr2["http"] = h2
                all_trace.append(tr2)
                if resp2.status == "ok":
                    plan.results[step.step_id] = dict(resp2.data or {})
                    plan.current_index += 1
                    continue
                resp = resp2

            miss = (resp.missing or ["unknown"])[0]
            auto = _auto_step_for_missing(miss, plan, user_text)
            if auto and inserts < _MAX_INSERT:
                lb2 = latest_board_id()
                if auto.inputs.get("board_id") == "$PREV.board_id" and lb2:
                    auto = _substitute_prev_refs(auto, lb2)
                elif not auto.inputs.get("board_id") and lb2:
                    auto = PlanStep(
                        step_id=auto.step_id,
                        agent=auto.agent,
                        ask=auto.ask,
                        inputs={**auto.inputs, "board_id": lb2},
                        depends_on=auto.depends_on,
                        outputs=auto.outputs,
                        purpose=auto.purpose,
                    )
                plan.steps.insert(plan.current_index, auto)
                inserts += 1
                logger.info(
                    "[a2a] reply status=need_info missing=%s — inserting %s.%s before step.",
                    resp.missing,
                    auto.agent,
                    auto.ask,
                )
                continue

            return {
                "plan": plan_to_dict(plan),
                "plan_trace": all_trace,
                "plan_execution_status": "error",
                "error_message": f"Missing: {resp.missing}",
                "http_status": 422,
            }

        if resp.status == "clarify_user":
            amb: dict[str, Any] = {}
            if resp.data.get("matches"):
                amb = {"kind": "multiple_cards", "matches": resp.data.get("matches")}
            elif resp.data.get("candidates"):
                amb = {"kind": "candidates", "values": resp.data.get("candidates")}
            q = (resp.clarification or "Please clarify.").strip()
            return {
                "plan": plan_to_dict(plan),
                "plan_trace": all_trace,
                "needs_clarification": True,
                "clarification_question": q,
                "ambiguous_entities": amb,
                "plan_execution_status": "clarify",
                "pending_plan_payload": {"plan": plan_to_dict(plan)},
                "http_status": 200,
                "parsed_response": {"clarification": True, "question": q},
            }

        # error
        return {
            "plan": plan_to_dict(plan),
            "plan_trace": all_trace,
            "plan_execution_status": "error",
            "error_message": resp.error or "Agent error",
            "http_status": 502,
        }

    parsed = _aggregate_parsed(plan, plan.results)
    return {
        "plan": plan_to_dict(plan),
        "plan_trace": all_trace,
        "parsed_response": parsed,
        "plan_execution_status": "ok",
        "http_status": 200,
        "error_message": "",
        "entities": _entities_from_results(plan.results),
        "intent": normalize_intent_label(plan.final_intent),
        "selected_tool": "a2a_plan",
    }


def _entities_from_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ent: dict[str, Any] = {}
    for data in results.values():
        if not isinstance(data, dict):
            continue
        for k in ("board_id", "list_id", "card_id", "resolved_board_name", "card_name", "list_name"):
            if data.get(k) is not None:
                ent[k] = data.get(k)
    return ent
