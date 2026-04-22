"""OrchestratorAgent — build_plan / resume_plan via structured LLM (catalog of agents + asks only)."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.base import Plan, PlanStep, new_plan_id, plan_from_dict, plan_to_dict
from app.llm import get_chat_model, invoke_chat_logged
from app.session_memory import memory_summary_for_planner

logger = logging.getLogger(__name__)

CATALOG = """
Allowed agents and asks (inputs must be short hints or $step_id.field references only).
PRD v3 intent hints (for final_intent naming): QUERY_BOARDS, QUERY_SEARCH, QUERY_NOTIFICATIONS, QUERY_CUSTOM_FIELDS,
CUSTOM_FIELD_SET, WEBHOOK_CREATE, CARD_MOVE, CARD_CREATE, etc.

- member: get_me | get_my_boards | get_member_cards | get_my_notifications | get_my_organizations | update_me | resolve_member
- board: resolve_board | get_board | get_board_lists | get_board_cards | get_board_labels | get_board_members | get_board_actions | create_board | update_board | delete_board | get_board_custom_fields | add_board_member | remove_board_member | get_board_memberships
- list: resolve_list | get_list_cards | create_list | update_list | archive_list | set_list_closed | set_list_pos
- card: resolve_card | get_card_details | create_card | update_card | move_card | delete_card | set_card_closed | remove_card_member | add_card_member | set_card_due | set_card_due_complete | get_card_custom_field_items | set_card_custom_field_item
- checklist: list_checklists | resolve_checklist | resolve_check_item | set_checkitem_state | create_checkitem | create_checklist | delete_checkitem
- label: resolve_label | add_label_to_card | remove_label_from_card | create_label_on_board | get_label
- comment: list_comments | create_comment | update_comment | delete_comment
- custom_field: get_board_custom_fields | create_custom_field | get_card_custom_field_items | set_card_custom_field_value | delete_custom_field
- webhook: list_webhooks | create_webhook | get_webhook | delete_webhook
- organization: get_my_organizations | get_organization | get_organization_boards | get_organization_members
- search: search | search_members
- notification: list_notifications | mark_all_notifications_read | update_notification
- attachment: list_attachments | add_url_attachment | delete_attachment

Reference outputs from prior steps using "$STEP_ID.field" (e.g. "$s1.board_id", "$s2.list_id", "$s3.card_id").
Typical flows:
- "all cards on board X": resolve_board -> get_board_cards (board_id from $s0)
- "move card A to list B": resolve_board -> resolve_card(card_hint) -> resolve_list(list_hint) -> move_card(card_id, target_list_id from $list step)
- "add card Title in List L": resolve_board -> resolve_list -> create_card(list_id, card_name)
- "find cards about onboarding": search (query in inputs_json)
- "show notifications": member get_my_notifications OR notification list_notifications
- "set custom field Priority on card X": resolve_board -> resolve_card -> custom_field get_board_custom_fields -> set_card_custom_field_value
- "mark [card] as done": resolve_board -> resolve_card -> card set_card_due_complete(dueComplete=true)
- "add checklist [name] to [card]": resolve_board -> resolve_card -> checklist create_checklist(name)
- "add item [X] to [checklist] on [card]": resolve_board -> resolve_card -> resolve_checklist -> create_checkitem
- "check off [item] on [card]": resolve_board -> resolve_card -> resolve_check_item (by card_id+item_name) -> set_checkitem_state
- "add label [name] to [card]": resolve_board -> resolve_card -> resolve_label -> add_label_to_card
- "assign [person] to [card]": resolve_board -> resolve_card -> member resolve_member -> card add_card_member
Do NOT put full user sentences into card_hint — use a short token from the user request (card title, list name, board name).
"""

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

    def build_plan(self, user_text: str, memory: dict[str, Any] | None) -> Plan:
        mem = memory or {}
        llm = get_chat_model(0).with_structured_output(_BuildPlan)
        summary = memory_summary_for_planner(mem)
        prompt = f"""You are the orchestrator for a Trello assistant. Decompose the user's request into a linear plan (DAG with depends_on).

{CATALOG}

Session memory (hints only):
{summary}

User message:
{user_text}

Rules:
- Start with board.resolve_board when any board-scoped action is needed unless memory already has board_id and the user did not name a different board.
- Use depends_on so list/card steps run after board resolution when they need board_id from a prior step.
- For move_card: inputs should reference card_id and target_list_id from resolve steps, e.g. "$s2.card_id" and "$s3.list_id".
- For create_card: include card_name as a SHORT title string when the user gave one; list_id as "$sx.list_id" from resolve_list.
- Keep inputs values short. Never copy the entire user message into a single field.
- Each step's inputs_json field must be a valid JSON object serialized as a string; when a step has no inputs, set inputs_json to {{}} (empty JSON object).
"""
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": "Output only valid structured plan steps."}, {"role": "user", "content": prompt}],
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
                meta={"user_text": user_text},
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
        plan = Plan(plan_id=pid, steps=steps, final_intent=out.final_intent, current_index=0, results={}, meta={"user_text": user_text})
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
        prompt = f"""The assistant was waiting for more information to continue an existing Trello plan.

{CATALOG}

Session memory:
{summary}

Pending plan (JSON):
{json.dumps(plan_to_dict(plan), ensure_ascii=False)[:12000]}

Blocked step (if any): {cur.step_id if cur else "none"} ask={cur.ask if cur else ""}

Latest user message (may be the answer):
{user_text}

Decide:
- If the user is continuing/clarifying (picking an option, giving a list name, confirming), set is_continuation=true and patch_inputs_json to a JSON object string with new fields (e.g. {{"list_hint":"Done"}}).
- If the user started a completely new task, set abandon_pending=true.
- patch_inputs_json must be valid JSON as a string; use {{}} if nothing to patch.
"""
        raw = invoke_chat_logged(
            llm,
            [{"role": "system", "content": "Structured resume only."}, {"role": "user", "content": prompt}],
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
