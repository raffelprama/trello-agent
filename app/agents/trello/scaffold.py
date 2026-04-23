"""ScaffoldAgent — AI-generated task scaffolding: cards with checklists, due dates, and member assignment."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.core.llm import get_chat_model, invoke_chat_logged
from app.tools import board as board_tools
from app.tools import card as card_tools
from app.tools import checklist as cl_tools

logger = logging.getLogger(__name__)

_GENERATE_SYSTEM = (
    "You are a project planning assistant. Generate a realistic, practical Trello task structure "
    "with actionable content and honest effort estimates. Return only the requested JSON structure."
)

_GENERATE_USER_TEMPLATE = """Generate a Trello task scaffold for the following topic:

Topic: {topic}
Cards to create: {n_cards}
Checklists per card: {checklists_hint}
Items per checklist: {items_hint}
{members_block}
For each card provide:
- name: a short, clear card title (specific and action-oriented, not just the topic)
- desc: 2-3 sentences describing the card's objective, what will be accomplished, and why it matters
- estimated_days: realistic number of working days to complete this card (be honest — a card with many complex items takes longer)
- assigned_member: the full name of one team member to own this card (choose from the list above, or null if no members provided)
- checklists: list of checklists, each with a clear name and step-by-step actionable items

Rules:
- Content must be realistic, specific, and directly related to the topic
- Checklist names should represent phases or categories (e.g. "Planning", "Implementation", "Testing")
- Each checklist item must be a concrete, actionable task starting with a verb
- Do not repeat items across checklists
- If multiple cards, each should cover a distinct aspect or phase of the topic
- Distribute team members across cards so no one is overloaded (if multiple members available)
- estimated_days must be at least 1
"""

_ESTIMATE_SYSTEM = (
    "You are a project planning assistant. Estimate realistic effort for a Trello card based on its content."
)

_ESTIMATE_USER_TEMPLATE = """Estimate the realistic number of working days to complete this Trello card:

Card name: {name}
Description: {desc}
Checklist count: {checklist_count}
Total checklist items: {item_count}

Provide:
- estimated_days: realistic working days (minimum 1, be practical — consider complexity, not just item count)
- reasoning: one sentence explaining the estimate
"""


class _ChecklistSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    items: list[str] = Field(default_factory=list)


class _CardSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    desc: str = ""
    estimated_days: int = Field(default=3, ge=1)
    assigned_member: str | None = None
    checklists: list[_ChecklistSpec] = Field(default_factory=list)


class _ScaffoldStructure(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cards: list[_CardSpec] = Field(default_factory=list)


class _DueEstimate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    estimated_days: int = Field(ge=1)
    reasoning: str = ""


class ScaffoldAgent(BaseAgent):
    name = "scaffold"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "build_task_scaffold":
            return self._build_task_scaffold(msg, ins)
        if ask == "set_smart_due":
            return self._set_smart_due(msg, ins)

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")

    # ------------------------------------------------------------------
    # build_task_scaffold
    # ------------------------------------------------------------------

    def _build_task_scaffold(self, msg: A2AMessage, ins: dict[str, Any]) -> A2AResponse:
        list_id = str(ins.get("list_id") or "").strip()
        if not list_id:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["list_id"])

        topic = str(ins.get("topic") or ins.get("task_topic") or "").strip()
        if not topic:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["topic"])

        n_cards = max(1, int(ins.get("n_cards") or 1))
        n_checklists_raw = ins.get("n_checklists")
        n_items_raw = ins.get("n_items")
        n_checklists: int | None = int(n_checklists_raw) if n_checklists_raw is not None else None
        n_items: int | None = int(n_items_raw) if n_items_raw is not None else None

        # Fetch board members for auto-assignment
        board_id = str(ins.get("board_id") or "").strip()
        member_map: dict[str, str] = {}  # lower_name → member_id
        member_names: list[str] = []
        if board_id:
            st_m, members = board_tools.get_board_members(board_id)
            if st_m < 400 and isinstance(members, list):
                for m in members:
                    if not isinstance(m, dict) or not m.get("id"):
                        continue
                    display = m.get("fullName") or m.get("username") or ""
                    if display:
                        member_map[display.lower()] = m["id"]
                        member_map[(m.get("username") or "").lower()] = m["id"]
                        member_names.append(display)

        structure = self._generate_structure(topic, n_cards, n_checklists, n_items, member_names)

        # Chain due dates: each card starts where the previous ended
        now_utc = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
        current_due = now_utc

        created_cards: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for card_spec in structure.cards:
            current_due = current_due + timedelta(days=max(1, card_spec.estimated_days))
            due_str = current_due.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            st, card = card_tools.create_card(
                list_id, card_spec.name,
                desc=card_spec.desc or None,
                due=due_str,
            )
            if st >= 400:
                errors.append({"name": card_spec.name, "error": f"HTTP {st}"})
                logger.warning("[scaffold] create_card failed name=%r st=%d", card_spec.name, st)
                continue

            card_id = card.get("id", "")

            # Auto-assign member
            assigned_name: str | None = None
            if card_spec.assigned_member and member_map:
                key = card_spec.assigned_member.strip().lower()
                mid = member_map.get(key) or next(
                    (v for k, v in member_map.items() if k and (key in k or k in key)), None
                )
                if mid:
                    st_a, _ = card_tools.add_member(card_id, mid)
                    if st_a < 400:
                        assigned_name = card_spec.assigned_member
                    else:
                        logger.warning("[scaffold] add_member failed name=%r st=%d", card_spec.assigned_member, st_a)

            # Create checklists + items
            created_checklists: list[dict[str, Any]] = []
            for cl_spec in card_spec.checklists:
                st2, cl = card_tools.post_card_checklist(card_id, cl_spec.name)
                if st2 >= 400:
                    logger.warning("[scaffold] create_checklist failed name=%r st=%d", cl_spec.name, st2)
                    continue
                cl_id = cl.get("id", "")
                created_items: list[str] = []
                for item_name in cl_spec.items:
                    st3, _ = cl_tools.create_checkitem(cl_id, item_name)
                    if st3 < 400:
                        created_items.append(item_name)
                    else:
                        logger.warning("[scaffold] create_checkitem failed name=%r st=%d", item_name, st3)
                created_checklists.append({"name": cl_spec.name, "items": created_items})

            created_cards.append({
                "card_id": card_id,
                "name": card_spec.name,
                "desc": card_spec.desc,
                "due": due_str,
                "estimated_days": card_spec.estimated_days,
                "assigned_member": assigned_name,
                "checklists": created_checklists,
            })
            logger.info(
                "[scaffold] created card=%r due=%s member=%r checklists=%d",
                card_spec.name, due_str, assigned_name, len(created_checklists),
            )

        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="ok",
            data={
                "scaffold_results": created_cards,
                "error_count": len(errors),
                "errors": errors,
                "list_id": list_id,
                "topic": topic,
                "cards_created": len(created_cards),
            },
        )

    # ------------------------------------------------------------------
    # set_smart_due
    # ------------------------------------------------------------------

    def _set_smart_due(self, msg: A2AMessage, ins: dict[str, Any]) -> A2AResponse:
        card_id = str(ins.get("card_id") or "").strip()
        if not card_id:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])

        # Fetch card details
        st, card = card_tools.get_card(card_id)
        if st >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st} fetching card")

        # Fetch checklists for complexity
        st2, checklists = card_tools.get_card_checklists(card_id)
        checklist_count = 0
        item_count = 0
        if st2 < 400 and isinstance(checklists, list):
            checklist_count = len(checklists)
            for cl in checklists:
                if isinstance(cl, dict):
                    items = cl.get("checkItems") or []
                    item_count += len(items) if isinstance(items, list) else 0

        estimate = self._estimate_due(
            name=card.get("name") or "",
            desc=card.get("desc") or "",
            checklist_count=checklist_count,
            item_count=item_count,
        )

        due_dt = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=estimate.estimated_days)
        due_str = due_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        st3, _ = card_tools.set_due(card_id, due_str)
        if st3 >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st3} setting due date")

        logger.info(
            "[scaffold] set_smart_due card_id=%s days=%d due=%s",
            card_id, estimate.estimated_days, due_str,
        )
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="ok",
            data={
                "card_id": card_id,
                "card_name": card.get("name"),
                "due": due_str,
                "estimated_days": estimate.estimated_days,
                "reasoning": estimate.reasoning,
            },
        )

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _generate_structure(
        self,
        topic: str,
        n_cards: int,
        n_checklists: int | None,
        n_items: int | None,
        member_names: list[str],
    ) -> _ScaffoldStructure:
        checklists_hint = f"exactly {n_checklists}" if n_checklists else "2–4 (choose the most logical groupings)"
        items_hint = f"exactly {n_items}" if n_items else "3–7 (actionable but not overwhelming)"
        members_block = (
            f"Team members available for assignment: {', '.join(member_names)}\n"
            if member_names else ""
        )

        prompt = _GENERATE_USER_TEMPLATE.format(
            topic=topic,
            n_cards=n_cards,
            checklists_hint=checklists_hint,
            items_hint=items_hint,
            members_block=members_block,
        )

        llm = get_chat_model(0).with_structured_output(_ScaffoldStructure)
        try:
            raw = invoke_chat_logged(
                llm,
                [{"role": "system", "content": _GENERATE_SYSTEM}, {"role": "user", "content": prompt}],
                operation="scaffold_generate",
            )
            result = raw if isinstance(raw, _ScaffoldStructure) else _ScaffoldStructure.model_validate(raw)
        except Exception as exc:
            logger.warning("[scaffold] LLM generation failed: %s — using fallback", exc)
            result = _ScaffoldStructure(cards=[_CardSpec(name=topic, desc="", checklists=[])])

        # Enforce count constraints
        result.cards = result.cards[:n_cards]
        for card in result.cards:
            if n_checklists:
                card.checklists = card.checklists[:n_checklists]
            if n_items:
                for cl in card.checklists:
                    cl.items = cl.items[:n_items]

        return result

    def _estimate_due(
        self,
        name: str,
        desc: str,
        checklist_count: int,
        item_count: int,
    ) -> _DueEstimate:
        prompt = _ESTIMATE_USER_TEMPLATE.format(
            name=name,
            desc=desc or "(none)",
            checklist_count=checklist_count,
            item_count=item_count,
        )
        llm = get_chat_model(0).with_structured_output(_DueEstimate)
        try:
            raw = invoke_chat_logged(
                llm,
                [{"role": "system", "content": _ESTIMATE_SYSTEM}, {"role": "user", "content": prompt}],
                operation="scaffold_estimate_due",
            )
            return raw if isinstance(raw, _DueEstimate) else _DueEstimate.model_validate(raw)
        except Exception as exc:
            logger.warning("[scaffold] estimate_due LLM failed: %s — using default 3 days", exc)
            # Fallback: 1 day per 3 items, minimum 1
            fallback_days = max(1, item_count // 3)
            return _DueEstimate(estimated_days=fallback_days, reasoning="fallback estimate")
