"""Execute Plan DAG via AgentBus — resolves $step.field refs, handles need_info / clarify / error."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import re

from app.agents.base import A2AMessage, Plan, PlanStep, new_task_id, parse_ref, plan_to_dict
from app.agents.bus import get_default_bus
from app.governance.intent_taxonomy import normalize_intent_label
from app.governance.plan_governance import (
    effective_confirm_duplicate_creations,
    effective_confirm_mutations,
    effective_dry_run,
    is_creation_step,
    is_destructive,
    is_mutating,
)
from app.core.state import ChatState
from app.services.trello_client import get_client
from app.tools import board as board_tools
from app.tools import list_ops as list_tools
from app.utils.resolution import levenshtein
from app.utils.trello_summaries import slim_result_for_answer

logger = logging.getLogger(__name__)

_MAX_INSERT = 8
_SLICE_REF_RE = re.compile(r"^\$([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\[:(\d+)\]$")


def _memory_card_id(mem: dict[str, Any]) -> Any:
    """Prefer explicit card_id, then last mentioned/focused (continuation)."""
    return mem.get("card_id") or mem.get("last_mentioned_card_id") or mem.get("last_card_id")


def _resolve_value(val: Any, results: dict[str, dict[str, Any]]) -> Any:
    if not isinstance(val, str):
        return val
    v = val.strip()
    m = _SLICE_REF_RE.match(v)
    if m:
        lst = (results.get(m.group(1)) or {}).get(m.group(2))
        return lst[:int(m.group(3))] if isinstance(lst, list) else lst
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
        if miss == "card_id":
            cid = _memory_card_id(mem)
            if cid:
                m[mk] = cid
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
        if not isinstance(data, dict):
            continue
        slim = slim_result_for_answer(data)
        out["step_summaries"][sid] = {k: slim[k] for k in list(slim.keys())[:24]}
        if "queried_board" in slim:
            out["queried_board"] = slim["queried_board"]
        if "cards" in slim:
            out["cards"] = slim["cards"]
        if "card" in slim:
            out["card"] = slim["card"]
        if "lists" in slim:
            out["lists"] = slim["lists"]
        if "labels" in slim:
            out["labels"] = slim["labels"]
        if "member" in slim:
            out["member"] = slim["member"]
        if "boards" in slim:
            out["boards"] = slim["boards"]
        if "checklists" in slim:
            out["checklists"] = slim["checklists"]
        if "comments" in slim:
            out["comments"] = slim["comments"]
        if "custom_fields" in slim:
            out["custom_fields"] = slim["custom_fields"]
        if "webhooks" in slim:
            out["webhooks"] = slim["webhooks"]
        if isinstance(slim.get("board"), dict):
            b = slim["board"]
            out["queried_board"] = {"id": b.get("id"), "name": b.get("name")}
        if "board_summary" in slim:
            out["board_summary"] = slim["board_summary"]
        if "scaffold_results" in slim:
            out["scaffold_results"] = slim["scaffold_results"]
    return out


def _destructive_confirm_question(step: PlanStep) -> str:
    return (
        f"This step is destructive: {step.agent}.{step.ask}. "
        "Reply with yes to proceed, or rephrase to cancel."
    )


def _norm_creation_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _creation_pair_conflict(planned: str, existing: str) -> bool:
    pn, en = _norm_creation_name(planned), _norm_creation_name(existing)
    if not pn or not en:
        return False
    if pn == en:
        return True
    shorter = min(len(pn), len(en))
    if shorter >= 3 and (pn in en or en in pn):
        return True
    lim = 2 if shorter >= 4 else 1
    return levenshtein(pn, en) <= lim


def _topic_conflicts_scaffold(topic: str, existing_card_name: str) -> bool:
    if _creation_pair_conflict(topic, existing_card_name):
        return True
    tn, en = _norm_creation_name(topic), _norm_creation_name(existing_card_name)
    if not tn or not en:
        return False
    if levenshtein(tn, en) <= 3:
        return True
    for w in re.split(r"[^\w]+", tn):
        if len(w) >= 4 and w in en:
            return True
    return False


def _resolve_list_and_board_for_cards(
    resolved: dict[str, Any],
    plan: Plan,
    mem: dict[str, Any],
) -> tuple[str | None, str | None]:
    list_id = resolved.get("list_id")
    board_id = resolved.get("board_id")
    if list_id:
        lid = str(list_id).strip()
        bid = str(board_id).strip() if board_id else ""
        if not bid:
            for data in reversed(list(plan.results.values())):
                if isinstance(data, dict) and data.get("board_id"):
                    bid = str(data["board_id"])
                    break
        if not bid and mem.get("board_id"):
            bid = str(mem.get("board_id"))
        return lid, bid or None
    if board_id:
        return None, str(board_id).strip()
    lid, bid = None, None
    for data in reversed(list(plan.results.values())):
        if not isinstance(data, dict):
            continue
        if not lid and data.get("list_id"):
            lid = str(data["list_id"])
        if not bid and data.get("board_id"):
            bid = str(data["board_id"])
    if not bid and mem.get("board_id"):
        bid = str(mem.get("board_id"))
    return lid, bid


def _existing_card_titles(list_id: str | None, board_id: str | None) -> list[str]:
    cards: list[dict[str, Any]] = []
    if list_id:
        st, raw = list_tools.get_list_cards(str(list_id))
        if st < 400 and isinstance(raw, list):
            cards = [c for c in raw if isinstance(c, dict)]
    elif board_id:
        st, raw = board_tools.get_board_cards(str(board_id))
        if st < 400 and isinstance(raw, list):
            cards = [c for c in raw if isinstance(c, dict)]
    return [str(c.get("name", "")) for c in cards if c.get("name")]


def _planned_names_from_resolved(step: PlanStep, resolved: dict[str, Any]) -> list[str]:
    a, k = step.agent.strip().lower(), step.ask.strip().lower()
    if a == "batch" and k == "create_cards":
        raw = resolved.get("names")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                raw = [n.strip() for n in raw.split(",") if n.strip()]
        return [str(x).strip() for x in (raw or []) if str(x).strip()]
    if a == "card" and k == "create_card":
        n = resolved.get("card_name") or resolved.get("name")
        return [str(n).strip()] if n and str(n).strip() else []
    if a == "scaffold" and k == "build_task_scaffold":
        topic = resolved.get("topic") or resolved.get("task_topic") or ""
        return [str(topic).strip()] if str(topic).strip() else []
    return []


def _duplicate_creation_conflicts(
    step: PlanStep,
    resolved: dict[str, Any],
    plan: Plan,
    mem: dict[str, Any],
) -> list[dict[str, Any]]:
    lid, bid = _resolve_list_and_board_for_cards(resolved, plan, mem)
    existing = _existing_card_titles(lid, bid)
    if not existing:
        return []
    sk = (step.agent.strip().lower(), step.ask.strip().lower())
    out: list[dict[str, Any]] = []
    if sk == ("scaffold", "build_task_scaffold"):
        topic = str(resolved.get("topic") or resolved.get("task_topic") or "").strip()
        if not topic:
            return []
        for en in existing:
            if _topic_conflicts_scaffold(topic, en):
                out.append({"planned": topic, "existing": en, "note": "topic_similarity"})
        return out
    for p in _planned_names_from_resolved(step, resolved):
        for e in existing:
            if _creation_pair_conflict(p, e):
                out.append({"planned": p, "existing": e, "note": "name_similarity"})
    return out


def _duplicate_creation_question(conflicts: list[dict[str, Any]], step: PlanStep) -> str:
    lines = [
        f"Creating via {step.agent}.{step.ask} may duplicate existing work. Similar cards already on this board/list:",
    ]
    for c in conflicts[:8]:
        lines.append(f"  — new: {c.get('planned')!r} vs existing: {c.get('existing')!r}")
    lines.append("Reply **yes** or **proceed** to create anyway, or **no** / **cancel** to stop.")
    return "\n".join(lines)


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

        if (
            step.agent == "card"
            and step.ask != "resolve_card"
            and not resolved.get("card_id")
        ):
            cid = _memory_card_id(mem)
            if cid:
                resolved["card_id"] = cid

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

        if (
            is_creation_step(step.agent, step.ask)
            and effective_confirm_duplicate_creations(mem if isinstance(mem, dict) else None)
            and str(mem.get("duplicate_creation_confirmed_for_plan") or "") != str(plan.plan_id)
        ):
            dup_conf = _duplicate_creation_conflicts(step, resolved, plan, mem if isinstance(mem, dict) else {})
            if dup_conf:
                qd = _duplicate_creation_question(dup_conf, step)
                return {
                    "plan": plan_to_dict(plan),
                    "plan_trace": all_trace,
                    "needs_clarification": True,
                    "clarification_question": qd,
                    "ambiguous_entities": {"kind": "duplicate_creation_confirm", "conflicts": dup_conf},
                    "plan_execution_status": "clarify",
                    "pending_plan_payload": {
                        "plan": plan_to_dict(plan),
                        "awaiting_duplicate_creation_confirm": True,
                    },
                    "http_status": 200,
                    "parsed_response": {"clarification": True, "question": qd},
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

        # Expand _foreach: iterate a resolved collection, dispatch one A2A call per item.
        if step.agent == "_foreach":
            source = resolved.get("source")
            if not isinstance(source, list):
                return {
                    "plan": plan_to_dict(plan),
                    "plan_trace": all_trace,
                    "plan_execution_status": "error",
                    "error_message": (
                        f"_foreach step {step.step_id}: 'source' must be a list, "
                        f"got {type(source).__name__!r}. Check that the prior step returns a 'cards' field."
                    ),
                    "http_status": 422,
                }
            limit = resolved.get("limit")
            if limit is not None:
                try:
                    source = source[:int(limit)]
                except (TypeError, ValueError):
                    pass
            apply_agent = str(resolved.get("agent") or "")
            apply_ask = str(resolved.get("ask") or "")
            item_id_field = str(resolved.get("item_id_field") or "id")
            # key_as: the input key name expected by the target agent (e.g. "card_id" for card ops)
            key_as = str(resolved.get("key_as") or ("card_id" if apply_agent == "card" else item_id_field))
            extra_inputs = dict(resolved.get("extra_inputs") or {})

            fe_success: list[dict[str, Any]] = []
            fe_errors: list[dict[str, Any]] = []
            for item in source:
                iid = item.get(item_id_field) if isinstance(item, dict) else str(item)
                fe_ctx: dict[str, Any] = {
                    "user_text": user_text,
                    "memory": mem,
                    "_resolved_inputs": {key_as: iid, **extra_inputs},
                }
                fe_msg = A2AMessage(
                    task_id=new_task_id(), frm="executor", to=apply_agent, ask=apply_ask, context=fe_ctx
                )
                fe_resp = bus.dispatch(fe_msg)
                if fe_resp.status == "ok":
                    fe_success.append({key_as: iid, **(fe_resp.data or {})})
                else:
                    fe_errors.append({key_as: iid, "error": fe_resp.error or fe_resp.status})

            logger.info(
                "[plan] _foreach plan_id=%s step=%s agent=%s ask=%s items=%d ok=%d err=%d",
                plan.plan_id, step.step_id, apply_agent, apply_ask,
                len(source), len(fe_success), len(fe_errors),
            )
            all_trace.append({
                "plan_id": plan.plan_id,
                "step_id": step.step_id,
                "agent": step.agent,
                "ask": step.ask,
                "status": "ok",
                "foreach_count": len(source),
                "success_count": len(fe_success),
                "error_count": len(fe_errors),
            })
            plan.results[step.step_id] = {
                "success_count": len(fe_success),
                "error_count": len(fe_errors),
                "results": fe_success[:50],
                "errors": fe_errors[:20],
            }
            plan.current_index += 1
            continue

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
