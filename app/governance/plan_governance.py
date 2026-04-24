"""Plan execution governance — mutating/destructive steps, confirmation heuristics."""

from __future__ import annotations

import re
from typing import Any

# (agent, ask) tuples that perform writes (skipped or simulated under dry_run).
MUTATING_STEPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("board", "create_board"),
        ("board", "update_board"),
        ("board", "delete_board"),
        ("board", "add_board_member"),
        ("board", "remove_board_member"),
        ("list", "create_list"),
        ("list", "update_list"),
        ("list", "archive_list"),
        ("list", "set_list_closed"),
        ("list", "set_list_pos"),
        ("card", "create_card"),
        ("card", "update_card"),
        ("card", "move_card"),
        ("card", "delete_card"),
        ("card", "set_card_closed"),
        ("card", "set_card_due"),
        ("card", "set_card_due_complete"),
        ("card", "add_card_member"),
        ("card", "remove_card_member"),
        ("card", "set_card_custom_field_item"),
        ("checklist", "set_checkitem_state"),
        ("checklist", "create_checkitem"),
        ("checklist", "create_checklist"),
        ("checklist", "delete_checkitem"),
        ("label", "add_label_to_card"),
        ("label", "remove_label_from_card"),
        ("label", "create_label_on_board"),
        ("comment", "create_comment"),
        ("comment", "update_comment"),
        ("comment", "delete_comment"),
        ("custom_field", "create_custom_field"),
        ("custom_field", "set_card_custom_field_value"),
        ("custom_field", "delete_custom_field"),
        ("webhook", "create_webhook"),
        ("webhook", "delete_webhook"),
        ("notification", "mark_all_notifications_read"),
        ("notification", "update_notification"),
        ("attachment", "add_url_attachment"),
        ("attachment", "delete_attachment"),
        ("member", "update_me"),
        ("batch", "mark_list_cards_complete"),
        ("batch", "archive_list_cards"),
        ("batch", "create_cards"),
        ("batch", "mark_checklist_items_complete"),
        ("batch", "mark_card_items_complete"),
        ("scaffold", "build_task_scaffold"),
        ("scaffold", "set_smart_due"),
        ("_foreach", "apply"),
    }
)

# Destructive — require confirmation when memory.settings.confirm_mutations is true.
DESTRUCTIVE_STEPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("board", "delete_board"),
        ("card", "delete_card"),
        ("checklist", "delete_checkitem"),
        ("comment", "delete_comment"),
        ("custom_field", "delete_custom_field"),
        ("webhook", "delete_webhook"),
        ("attachment", "delete_attachment"),
        ("label", "remove_label_from_card"),
        ("board", "remove_board_member"),
        ("card", "remove_card_member"),
        ("list", "archive_list"),
        ("list", "set_list_closed"),
        ("batch", "archive_list_cards"),
    }
)

# Creation / bulk-add — duplicate-risk gate before first such step per plan (optional confirm).
CREATION_STEPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("card", "create_card"),
        ("batch", "create_cards"),
        ("scaffold", "build_task_scaffold"),
        ("list", "create_list"),
        ("checklist", "create_checklist"),
    }
)


def step_key(agent: str, ask: str) -> tuple[str, str]:
    return (agent.strip().lower(), ask.strip().lower())


def is_mutating(agent: str, ask: str) -> bool:
    return step_key(agent, ask) in MUTATING_STEPS


def is_destructive(agent: str, ask: str) -> bool:
    return step_key(agent, ask) in DESTRUCTIVE_STEPS


def is_creation_step(agent: str, ask: str) -> bool:
    return step_key(agent, ask) in CREATION_STEPS


def plan_has_destructive(plan_steps: list[Any]) -> bool:
    from app.agents.base import PlanStep

    for st in plan_steps:
        if not isinstance(st, PlanStep):
            continue
        if is_destructive(st.agent, st.ask):
            return True
    return False


_CONFIRM_RE = re.compile(
    r"^\s*(yes|yep|yeah|y|confirm|confirmed|ok|okay|proceed|go ahead|do it|create anyway|continue)\s*[.!]?\s*$",
    re.I,
)

_REJECT_PLAN_RE = re.compile(
    r"^\s*(no|nope|nah|stop|cancel|abort|don\'t|do not|skip)\b",
    re.I,
)


def user_confirms_destructive(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return False
    if _CONFIRM_RE.match(t):
        return True
    return False


def user_confirms_duplicate_creation(user_text: str) -> bool:
    """User explicitly allows create despite similar existing cards (same accept patterns as destructive)."""
    return user_confirms_destructive(user_text)


def user_rejects_duplicate_creation(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return False
    return bool(_REJECT_PLAN_RE.match(t))


def effective_dry_run(memory: dict[str, Any] | None, state_override: bool | None = None) -> bool:
    if state_override is not None:
        return bool(state_override)
    if not memory:
        return False
    s = memory.get("settings")
    if isinstance(s, dict) and s.get("dry_run"):
        return True
    return bool(memory.get("dry_run"))


def effective_confirm_mutations(memory: dict[str, Any] | None) -> bool:
    if not memory:
        return True
    s = memory.get("settings")
    if isinstance(s, dict) and "confirm_mutations" in s:
        return bool(s.get("confirm_mutations"))
    return True


def effective_confirm_duplicate_creations(memory: dict[str, Any] | None) -> bool:
    if not memory:
        return True
    s = memory.get("settings")
    if isinstance(s, dict) and "confirm_duplicate_creations" in s:
        return bool(s.get("confirm_duplicate_creations"))
    return True
