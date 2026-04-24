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
  get_member_cards: inputs: optional member_id (default **me** for the signed-in user); optional **board_id** — when set, return only cards on that board (filtered via each card's idBoard). Optional Trello params: filter, fields. When the user names another person, resolve_member first, then pass member_id=$sN.member_id and board_id=$s0.board_id.
- board: resolve_board | get_board | get_board_lists | get_board_cards | get_board_labels | get_board_members | get_board_actions | create_board | update_board | delete_board | get_board_custom_fields | add_board_member | remove_board_member | get_board_memberships | get_board_summary
- list: resolve_list | get_list_cards | create_list | update_list | archive_list | set_list_closed | set_list_pos
- card: resolve_card | get_card_details | create_card | update_card | move_card | delete_card | set_card_closed | remove_card_member | add_card_member | set_card_due | set_card_due_complete | get_card_custom_field_items | set_card_custom_field_item
- checklist: list_checklists | resolve_checklist | resolve_check_item | set_checkitem_state | create_checkitem | create_checklist | delete_checkitem
  Trello hierarchy: board → list → **card** → **checklist** → **check item** (checkbox line). Card **dueComplete** (due-date checkmark) is NOT a checklist; never use set_card_due_complete for checklist/checkbox/check-item wording.
  resolve_checklist: resolves checklist on a card. inputs: card_id, checklist_name (optional if inferrable); optional **item_name** — same string as the checklist line you will add or toggle; when checklist_name is omitted, the assistant **infers** the checklist if (a) the card has only one checklist, or (b) **exactly one** checklist already contains a matching item. optional create_if_missing (default true when a named checklist is missing on add-item flows)
  resolve_check_item: inputs: card_id, item_name; optional checklist_id from a prior resolve_checklist step; **or** checklist_name + item_name + card_id to scope the item to one checklist (preferred when the user names both). **outputs: check_item_id, checklist_id** — in plan steps use outputs ["check_item_id"] and reference **$sN.check_item_id** (underscore) for the next step.
  set_checkitem_state: inputs: card_id, **check_item_id** (from $sN.check_item_id), state ("complete"|"incomplete", default "complete")
  create_checklist: ONLY when the user explicitly asks to create a brand-new checklist with no items. inputs: card_id, name
  RULE: for "add item to checklist X", use resolve_checklist (find-or-create). For "check off / set / tick **one** checklist item", use resolve_checklist → resolve_check_item → set_checkitem_state — NOT batch.mark_card_items_complete and NOT card.set_card_due_complete.
- label: resolve_label | add_label_to_card | remove_label_from_card | create_label_on_board | get_label
  resolve_label inputs: board_id, label_name (the label name or color, e.g. "red", "D-1", "Priority")
- comment: list_comments | create_comment | update_comment | delete_comment
- custom_field: get_board_custom_fields | create_custom_field | get_card_custom_field_items | set_card_custom_field_value | delete_custom_field
- webhook: list_webhooks | create_webhook | get_webhook | delete_webhook
- organization: get_my_organizations | get_organization | get_organization_boards | get_organization_members
- search: search | search_members
- notification: list_notifications | mark_all_notifications_read | update_notification
- attachment: list_attachments | add_url_attachment | delete_attachment
- batch: mark_list_cards_complete | archive_list_cards | create_cards
         | mark_checklist_items_complete | mark_card_items_complete
  (handles iteration internally — preferred for bulk ops on an entire list or checklist)
  create_cards inputs: list_id, names (JSON array of card name strings, e.g. ["task1","task2"])
  mark_checklist_items_complete inputs: checklist_id, card_id, state ("complete"|"incomplete", default "complete") — **only** when the user asked to complete **all** items in that checklist
  mark_card_items_complete inputs: card_id, state ("complete"|"incomplete", default "complete") — **only** when the user asked to check **every** checklist item on the card (all checklists). **Never** use this for a single named checklist item.
- scaffold: build_task_scaffold | set_smart_due
  build_task_scaffold: AI-generates card names, descriptions, checklists, due dates, and member assignments
    inputs: list_id, topic (task/project subject), n_cards (int, default 1),
            n_checklists (int, optional), n_items (int, optional),
            board_id (pass $s0.board_id — enables auto member assignment)
  set_smart_due: AI estimates realistic due date for an existing card based on its content/complexity
    inputs: card_id
- _foreach: apply — iterate a prior step's collection; dispatch one agent action per item
  inputs_json: {"source":"$sX.cards","item_id_field":"id","key_as":"card_id","agent":"card","ask":"<ask>","extra_inputs":{<literal fields>},"limit":<optional int — first N items only>}

Reference outputs from prior steps using "$STEP_ID.field" (e.g. "$s1.board_id", "$s2.list_id", "$s3.card_id"). **Checklist item ID:** prefer **$sN.check_item_id** after resolve_check_item (canonical); **checkitem_id** is also present on the same step result as an alias if needed.
Typical flows:
- "all cards on board X": resolve_board -> get_board_cards (board_id from $s0)
- "cards on board X assigned to / with member [person]" / "which cards on [board] have [username]" / "under [board], cards for raffel6": **NOT** get_board_cards alone — resolve_board -> member resolve_member(board_id=$s0.board_id, member_hint=…) -> member get_member_cards(member_id=$s1.member_id, board_id=$s0.board_id). Do **not** list every card on the board when the user asked only for cards that include that assignee.
- "my cards on board X" / "cards assigned to me on [board]": resolve_board -> member get_member_cards(board_id=$s0.board_id) (omit member_id or use "me")
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
- "add item [X] to [checklist] on [card]" / "set checklist [name] item [X]": resolve_board -> resolve_card -> checklist resolve_checklist(checklist_name=hint) -> checklist create_checkitem(checklist_id=$sN.checklist_id)
- "add item [X]" / "checklist item [X]" on [card] **without** naming the checklist: resolve_board -> resolve_card -> **resolve_checklist(card_id, item_name=X)** (same full item text) -> create_checkitem OR resolve_check_item + set_checkitem_state if the user means check off an existing line — **always pass item_name on resolve_checklist** when checklist_name is omitted so the checklist can be inferred.
- "check off / set checklist item / tick checkbox" for **one** named item (especially when the user names the **checklist** and the **item** text): resolve_board -> resolve_card(card_hint = **the card title only**, not the checklist item text) -> resolve_checklist(checklist_name=…) -> resolve_check_item(checklist_id=$sN.checklist_id, item_name=short distinctive substring of the item) -> set_checkitem_state(check_item_id=$sM.check_item_id, state="complete") where $sM is the resolve_check_item step
  Alternate when both names are in one step: resolve_check_item(card_id=…, checklist_name=…, item_name=…) -> set_checkitem_state(check_item_id=$sM.check_item_id, …) — still resolve_board + resolve_card first for card_id.
- "check off [item] on [card]" (checklist not named): resolve_board -> resolve_card -> resolve_check_item (card_id+item_name only) -> set_checkitem_state(check_item_id=$sM.check_item_id, …)
- **Forbidden for single-item checklist toggles:** batch.mark_checklist_items_complete (unless all items in that checklist), batch.mark_card_items_complete, _foreach over all cards, card.set_card_due_complete — those are for whole checklist/card/board scopes, not one checkbox line.
- "add label [name] to [card]": resolve_board -> resolve_card -> label resolve_label(label_name=hint) -> label add_label_to_card
- "assign [person] to [card]": resolve_board -> resolve_card -> member resolve_member -> card add_card_member
- "summarize the board" / "board status" / "how is the board doing" / "progress report" / "I want to summarize": resolve_board -> board get_board_summary (returns completion %, per-member stats, due-date breakdown, recommendations)
- "build me a card for X" / "create a task scaffold for Y" / "generate N cards with checklists for Z":
    resolve_board -> resolve_list -> scaffold build_task_scaffold(list_id=$s1.list_id, board_id=$s0.board_id, topic="Z", n_cards=N)
  - Always pass board_id=$s0.board_id — enables auto due date + auto member assignment
  - Only specify n_checklists/n_items if the user explicitly stated a count; otherwise omit (AI decides)
  - topic must be a short subject phrase (e.g. "build a website", "marketing campaign")
- "give this card a due date" / "set realistic due for card X" / "when should card X be done":
    resolve_board -> resolve_card -> scaffold set_smart_due(card_id=$s1.card_id)
- "add [color/name] label to card X": resolve_board -> resolve_card -> label resolve_label(label_name=hint) -> label add_label_to_card
- "set all items in checklist X to done" / "check off checklist X":
    resolve_board -> resolve_card -> resolve_checklist -> batch mark_checklist_items_complete(checklist_id=$s2.checklist_id, card_id=$s1.card_id)
- "uncheck all items in checklist X":
    resolve_board -> resolve_card -> resolve_checklist -> batch mark_checklist_items_complete(checklist_id=$s2.checklist_id, card_id=$s1.card_id, state="incomplete")
- "set all checklist items on card X to done" / "mark everything on card X complete":
    resolve_board -> resolve_card -> batch mark_card_items_complete(card_id=$s1.card_id)
- "uncheck everything on card X":
    resolve_board -> resolve_card -> batch mark_card_items_complete(card_id=$s1.card_id, state="incomplete")
Do NOT put full user sentences into card_hint — use the card title, list name, or board name only. Long lines belong in resolve_check_item.item_name (checklist checkbox text), not card_hint.
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

Board naming: if session memory includes a line **boards you have access to (…)**, use an **exact** name from that list for board resolution hints (e.g. user says "board test" → prefer board_hint **Test** if listed), not a guessed variant.

Checklist vs card completion (analyzer must not conflate):
- If the user names a **checklist** and/or a **checklist item** / checkbox / "checklist item" / "subtask" line on a card → they mean **checklist check items** (suggested_final_intent like CHECKLIST_ITEM_SET), **not** CARD_SET_DUE_COMPLETE. Phrases like "set checklist to true" on an **item** are checklist state, not the due-date checkmark.
- CARD_SET_DUE_COMPLETE applies only when they mean the card's **due date is finished** (dueComplete), without targeting a named checklist line.

Cards filtered by assignee on a board: If the user asks which cards on a **named board** have / include / are assigned to a **specific member** (username or person name), set **required_entities** to include **board** and **member** and describe in reasoning that the assistant should list that member's cards **restricted to that board** (not all board cards). suggested_final_intent e.g. QUERY_BOARD_CARDS_BY_MEMBER.

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
- **Checklist item (one checkbox)** vs **card dueComplete** vs **bulk**: If the user names a checklist and/or a specific item line to check/uncheck, plan: resolve_card → resolve_checklist → resolve_check_item → set_checkitem_state. Do **not** use set_card_due_complete. Do **not** use batch.mark_card_items_complete or mark_card_items_complete unless they asked for **all** items in that checklist or **all** checklist lines on the card. Do **not** use _foreach over board cards for a single checklist item.
- CARD_SET_DUE_COMPLETE vs CARD_MOVE: if the user wants the due checkmark (dueComplete), use card set_card_due_complete — never move_card to Done unless they asked to move to the Done list/column.
- **card_hint** for checklist flows must be the **card's title** (short but distinctive). Do **not** put the checklist item's long text into card_hint — that belongs in resolve_check_item.item_name or **resolve_checklist.item_name** when inferring the checklist.
- Start with board.resolve_board when any board-scoped action is needed unless memory already has board_id and the user did not name a different board.
- Use depends_on so list/card steps run after board resolution when they need board_id from a prior step.
- For move_card: inputs should reference card_id and target_list_id from resolve steps, e.g. "$s2.card_id" and "$s3.list_id".
- For create_card: include card_name as a SHORT title string when the user gave one; list_id as "$sx.list_id" from resolve_list.
- Keep inputs values short. Never copy the entire user message into a single field.
- Each step's inputs_json field must be a valid JSON object serialized as a string; when a step has no inputs, set inputs_json to {{}} (empty JSON object).
- Due dates: if the user says "tomorrow", "next Friday", etc., convert to ISO 8601 UTC for `due` on create_card / set_card_due using the reference time at the top of session memory.
- Overdue / late / past-due questions: include a read step that returns cards with `due` and `dueComplete` (e.g. get_board_cards), then the answer can compare each card to reference UTC; do not assume overdue without that data.
- **Cards on a board assigned to a specific member:** resolve_board -> resolve_member(member_hint) -> get_member_cards(member_id=$s1.member_id, board_id=$s0.board_id). Do **not** use get_board_cards for that intent — it returns all cards and drops assignee info.
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

Decide — read BOTH signal types below before choosing:

**NEW TASK signals → abandon_pending=true (ignore the pending plan entirely)**
Any of these means the user started a fresh request, even if the message contains a name that could answer the blocked step:
- Complete sentence with a primary action verb directed at a Trello resource: "I want to see…", "show me…", "create…", "add…", "move…", "get…", "list…", "i want to…", "can you…"
- Multi-word request describing what to do AND what to do it on (e.g. "i want to see card under Test board", "show all cards in On Going")
- Any phrasing using first-person intent: "I want", "I'd like", "let me see", "saya mau", "tampilkan"
- A full question about Trello: "what cards are…", "how many…", "which board…"
→ Set abandon_pending=true, patch_inputs_json="{{}}"

**CONTINUATION signals → is_continuation=true**
Only treat as a continuation when the message is a SHORT, DIRECT answer to the specific blocked step question — and contains NO independent action verb or resource reference beyond answering that one question:
- Single word or short phrase: a name, a color, a number, "yes", "no", "confirm", "ok"
- Picking from a list the assistant presented: "the second one", "Done", "On Going", "red"
- Affirmation or negation to a yes/no question: "yeah go ahead", "no cancel it"
→ Set is_continuation=true, patch_inputs_json with the answered field

**Examples**
Blocked step: resolve_board, ask=resolve_board
- "Test" → continuation (just a board name)
- "i want to see card under Test board" → NEW TASK (full intent sentence with action verb + resource)
- "use the Test board" → NEW TASK (action-phrased intent)
- "Test board" → continuation (just naming the board)

Blocked step: resolve_list, ask=resolve_list
- "Done" → continuation
- "show me cards in Done" → NEW TASK
- "the Done list" → continuation

**Rule**: If unsure, prefer abandon_pending=true. It is safer to rebuild a plan than to misinterpret a new request.

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
