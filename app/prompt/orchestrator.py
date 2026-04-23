"""OrchestratorAgent — catalog and user/system prompts for build_plan / resume_plan."""

from __future__ import annotations

import json
from typing import Any

# Allowed agents and asks (keep in sync with OrchestratorAgent capabilities).
ORCHESTRATOR_CATALOG = """
Allowed agents and asks (inputs must be short hints or $step_id.field references only).
PRD v3 intent hints (for final_intent naming): QUERY_BOARDS, QUERY_SEARCH, QUERY_NOTIFICATIONS, QUERY_CUSTOM_FIELDS,
CUSTOM_FIELD_SET, WEBHOOK_CREATE, CARD_MOVE, CARD_SET_DUE_COMPLETE, CARD_CREATE, SUMMARIZE_BOARD, etc.

- member: get_me | get_my_boards | get_member_cards | get_my_notifications | get_my_organizations | update_me | resolve_member
- board: resolve_board | get_board | get_board_lists | get_board_cards | get_board_labels | get_board_members | get_board_actions | create_board | update_board | delete_board | get_board_custom_fields | add_board_member | remove_board_member | get_board_memberships | get_board_summary
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
- batch: mark_list_cards_complete | archive_list_cards | create_cards
  (handles iteration internally — preferred for bulk ops on an entire list)
  create_cards inputs: list_id, names (JSON array of card name strings, e.g. ["task1","task2"])
- _foreach: apply — iterate a prior step's collection; dispatch one agent action per item
  inputs_json: {"source":"$sX.cards","item_id_field":"id","key_as":"card_id","agent":"card","ask":"<ask>","extra_inputs":{<literal fields>},"limit":<optional int — first N items only>}

Reference outputs from prior steps using "$STEP_ID.field" (e.g. "$s1.board_id", "$s2.list_id", "$s3.card_id").
Typical flows:
- "all cards on board X": resolve_board -> get_board_cards (board_id from $s0)
- "move card A to list B": resolve_board -> resolve_card(card_hint) -> resolve_list(list_hint) -> move_card(card_id, target_list_id from $list step)
- "add card Title in List L": resolve_board -> resolve_list -> create_card(list_id, card_name)
- "find cards about onboarding": search (query in inputs_json)
- "list/show my boards", "all the board(s)", "see all boards", "saya mau liat semua board", or any phrasing (in any language) that asks to list/enumerate/show all boards the user has access to: **always use member get_my_boards** — never use board.resolve_board for this intent
- "show notifications": member get_my_notifications OR notification list_notifications
- "set custom field Priority on card X": resolve_board -> resolve_card -> custom_field get_board_custom_fields -> set_card_custom_field_value
- "move [card] to Done" / "put [card] in the Done list" / "move to Done column" → CARD_MOVE: resolve_board -> resolve_card -> resolve_list(list_hint Done) -> move_card (does NOT set dueComplete)
- "mark [card] as done" / "mark complete" / "set due complete" / "[card] is finished" → CARD_SET_DUE_COMPLETE: resolve_board -> resolve_card -> card set_card_due_complete(dueComplete=true) (Trello due badge; does NOT move the card or checklist items)
- If the user is vague ("set [card] to done", "[card] is done") and session memory shows a list named "Done" on the board, the analyzer must ask for clarification before planning — do not guess move vs mark-complete in the planner alone
- "add checklist [name] to [card]": resolve_board -> resolve_card -> checklist create_checklist(name)
- "add item [X] to [checklist] on [card]": resolve_board -> resolve_card -> resolve_checklist -> create_checkitem
- "check off [item] on [card]": resolve_board -> resolve_card -> resolve_check_item (by card_id+item_name) -> set_checkitem_state
- "add label [name] to [card]": resolve_board -> resolve_card -> resolve_label -> add_label_to_card
- "assign [person] to [card]": resolve_board -> resolve_card -> member resolve_member -> card add_card_member
- "summarize the board" / "board status" / "how is the board doing" / "progress report" / "I want to summarize": resolve_board -> board get_board_summary (returns completion %, per-member stats, due-date breakdown, recommendations)
Do NOT put full user sentences into card_hint — use a short token from the user request (card title, list name, board name).
"""

ANALYZE_SYSTEM = (
    "You output only the requested structured fields. Do not emit a step list or tool calls; "
    "a separate planner will build the executable DAG."
)

ANALYZE_USER_TEMPLATE = """Analyze the user's message for a Trello assistant. This is stage 1 only: no plan steps yet.

Session memory (hints only):
{memory_summary}

User message:
{user_text}

Produce structured output with:
- user_expectation: one sentence — what the user actually wants done.
- analysis: short paragraph — ambiguities, implicit references (e.g. "this card"), constraints, missing info.
- reasoning: ordered high-level steps the assistant should take in natural language only (NOT agent.ask names, NOT JSON).
- required_entities: list of entity types to resolve (e.g. board, list, card, member, label) — use lowercase tokens.
- suggested_final_intent: a short hint label only (e.g. CARD_MOVE, CARD_SET_DUE_COMPLETE, QUERY_BOARDS) — the planner may override.
- needs_intent_clarification: boolean — true ONLY when "done" is ambiguous between (A) moving the card to a list named Done and (B) marking the card's due as complete (dueComplete), per the rules below.
- clarification_question: string — if needs_intent_clarification is true, one short question for the user (e.g. "Move this card to the Done list, or mark the due date as complete (checkmark)?"); otherwise "".

Done vs complete (not checklist items; card-level dueComplete only):
- **CRITICAL — not ambiguous:** If the user uses **mark** together with **done** or **complete** anywhere (e.g. "mark Ai2 done", "set the Ai2 to mark done", "mark the complete", typos like "set the mark the complete"), OR **set** … **to** **done** without naming the Done **list/column** (e.g. "set the card Ai to done"), that always means **dueComplete / checkmark** → suggested_final_intent CARD_SET_DUE_COMPLETE; **needs_intent_clarification MUST be false**. Do not ask move-vs-mark for those.
- If the user clearly means a list/column only: "move to Done", "put in Done list", "Done column" (without mark+complete phrasing above) → CARD_MOVE; needs_intent_clarification=false.
- If they clearly mean completion without moving: "set due complete", "finished", "mark as done" → CARD_SET_DUE_COMPLETE; needs_intent_clarification=false.
- **Ambiguous (clarify only here):** They use "done" or "complete" **without** "mark", **without** "set … to done", and **without** "move"/"list"/"column" phrasing, AND session memory's "lists on board:" includes **Done**, e.g. "set X done" (no **to** before **done**) or "X is done" only → needs_intent_clarification=true.
- If there is no Done list in session memory, prefer CARD_SET_DUE_COMPLETE for vague "done" phrasing; needs_intent_clarification=false.
- If **pending_clarification** in session memory is about move-vs-mark and the user replies with mark/complete/due/checkmark wording, set CARD_SET_DUE_COMPLETE and needs_intent_clarification=false.

The session memory block begins with a reference time (UTC, optional local). Use it when the user says "tomorrow", "today", "overdue", or relative deadlines — reflect that in analysis and reasoning.
"""


BUILD_PLAN_SYSTEM = "Output only valid structured plan steps."

BUILD_PLAN_USER_TEMPLATE = """You are the orchestrator for a Trello assistant. Decompose the user's request into a linear plan (DAG with depends_on).

{catalog}

Session memory (hints only):
{memory_summary}

User message:
{user_text}

{analysis_block}Rules:
- CARD_SET_DUE_COMPLETE vs CARD_MOVE: if the user wants the due checkmark (dueComplete), use card set_card_due_complete — never move_card to Done unless they asked to move to the Done list/column.
- Start with board.resolve_board when any board-scoped action is needed unless memory already has board_id and the user did not name a different board.
- Use depends_on so list/card steps run after board resolution when they need board_id from a prior step.
- For move_card: inputs should reference card_id and target_list_id from resolve steps, e.g. "$s2.card_id" and "$s3.list_id".
- For create_card: include card_name as a SHORT title string when the user gave one; list_id as "$sx.list_id" from resolve_list.
- Keep inputs values short. Never copy the entire user message into a single field.
- Each step's inputs_json field must be a valid JSON object serialized as a string; when a step has no inputs, set inputs_json to {{}} (empty JSON object).
- Due dates: if the user says "tomorrow", "next Friday", etc., convert to ISO 8601 UTC for `due` on create_card / set_card_due using the reference time at the top of session memory.
- Overdue / late / past-due questions: include a read step that returns cards with `due` and `dueComplete` (e.g. get_board_cards), then the answer can compare each card to reference UTC; do not assume overdue without that data.
- Context: if the user just viewed or discussed one card and now says "update the description", "set due", etc. without naming a card, reuse that same card: `resolve_card` with an empty `card_hint` is OK (session memory supplies focus), or reference the prior step's `card_id`. Do not switch to a different card from a bulk list unless the user names it.
"""

RESUME_PLAN_SYSTEM = "Structured resume only."

RESUME_PLAN_USER_TEMPLATE = """The assistant was waiting for more information to continue an existing Trello plan.

{catalog}

Session memory:
{memory_summary}

Pending plan (JSON):
{plan_json}

Blocked step (if any): {blocked_step_id} ask={blocked_ask}

Latest user message (may be the answer):
{user_text}

Decide:
- If the user is continuing/clarifying (picking an option, giving a list name, confirming), set is_continuation=true and patch_inputs_json to a JSON object string with new fields (e.g. {{"list_hint":"Done"}}).
- If the user started a completely new task, set abandon_pending=true.
- patch_inputs_json must be valid JSON as a string; use {{}} if nothing to patch.
"""


def format_analyze_user(*, memory_summary: str, user_text: str) -> str:
    return ANALYZE_USER_TEMPLATE.format(
        memory_summary=memory_summary,
        user_text=user_text,
    )


def format_build_plan_user(
    *,
    memory_summary: str,
    user_text: str,
    catalog: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> str:
    cat = ORCHESTRATOR_CATALOG if catalog is None else catalog
    if analysis:
        blob = json.dumps(analysis, ensure_ascii=False, indent=2)
        analysis_block = (
            "Analyzer output (use to inform the plan; do not paste this text as inputs_json):\n"
            f"{blob}\n\n"
        )
    else:
        analysis_block = ""
    return BUILD_PLAN_USER_TEMPLATE.format(
        catalog=cat.strip(),
        memory_summary=memory_summary,
        user_text=user_text,
        analysis_block=analysis_block,
    )


def format_resume_plan_user(
    *,
    memory_summary: str,
    user_text: str,
    plan_dict: dict[str, Any],
    blocked_step_id: str,
    blocked_ask: str,
    catalog: str | None = None,
    plan_json_max_chars: int = 12000,
) -> str:
    cat = ORCHESTRATOR_CATALOG if catalog is None else catalog
    plan_json = json.dumps(plan_dict, ensure_ascii=False)[:plan_json_max_chars]
    return RESUME_PLAN_USER_TEMPLATE.format(
        catalog=cat.strip(),
        memory_summary=memory_summary,
        plan_json=plan_json,
        blocked_step_id=blocked_step_id,
        blocked_ask=blocked_ask,
        user_text=user_text,
    )
