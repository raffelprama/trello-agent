"""Prompts for the BulkOrchestratorAgent — focused catalog for bulk/iteration tasks."""

from __future__ import annotations

BULK_CATALOG = """
Allowed agents for bulk tasks (inputs are short hints or $step_id.field refs only):

- board: resolve_board
- list: resolve_list | get_list_cards
- board: get_board_cards
- batch: mark_list_cards_complete | archive_list_cards | create_cards
  (batch handles iteration internally — single-step, preferred for common bulk ops)
  create_cards inputs: list_id, names (JSON array of card name strings, e.g. ["task1","task2","task3"])
- _foreach: apply — iterate a prior step's collection and dispatch one agent action per item
  inputs_json fields: source ($sX.cards or $sX.lists), item_id_field ("id"),
  key_as (input key name for the agent — use "card_id" for card ops), agent, ask, extra_inputs (literal dict),
  limit (optional int — keep only the first N items of source, e.g. "limit": 2)

Reference: "$s0.board_id", "$s1.list_id", "$s1.cards"

Common bulk flows:
- "add N cards named X1…XN to [list]":
    resolve_board → resolve_list → batch.create_cards(list_id=$s1.list_id, names=["X1","X2",...])
- "mark all cards in [list] as done/complete":
    resolve_board → resolve_list → batch.mark_list_cards_complete(list_id=$s1.list_id)
  or: resolve_board → resolve_list → _foreach(source=$s1.cards, item_id_field=id, key_as=card_id, agent=card, ask=set_card_due_complete, extra_inputs={"dueComplete":true})
- "archive / close all cards in [list]":
    resolve_board → resolve_list → batch.archive_list_cards(list_id=$s1.list_id)
- "mark all cards on the board as done":
    resolve_board → board.get_board_cards(board_id=$s0.board_id) → _foreach(source=$s1.cards, item_id_field=id, key_as=card_id, agent=card, ask=set_card_due_complete, extra_inputs={"dueComplete":true})
- "mark the first 2 cards in [list] as done":
    resolve_board → resolve_list → get_list_cards → _foreach(source=$s2.cards, limit=2, key_as=card_id, agent=card, ask=set_card_due_complete, extra_inputs={"dueComplete":true})
"""

BULK_BUILD_PLAN_SYSTEM = "Output only valid structured plan steps for a bulk Trello operation."

BULK_BUILD_PLAN_USER_TEMPLATE = """You are the orchestrator for a Trello assistant handling a BULK task.
Build a linear plan that applies the same action to every item in a collection.

{catalog}

Session memory:
{memory_summary}

User message:
{user_text}

Rules:
- Start with board.resolve_board unless memory already has board_id and the user did not name a different board.
- Resolve the list by name with list.resolve_list before using its id.
- Use batch for built-in bulk operations (simpler, single step, preferred).
- Use _foreach when you need more control over which card action to apply.
- Keep inputs_json values short — only hints and $step.field refs. Never copy the full user message.
- Each step's inputs_json must be valid JSON as a string; use {{}} if no inputs.
"""


def format_bulk_build_plan_user(*, memory_summary: str, user_text: str) -> str:
    return BULK_BUILD_PLAN_USER_TEMPLATE.format(
        catalog=BULK_CATALOG.strip(),
        memory_summary=memory_summary,
        user_text=user_text,
    )
