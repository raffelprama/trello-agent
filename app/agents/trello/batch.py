"""BatchAgent — bulk card operations: iterate a list's cards and apply an action to each."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import card as card_tools
from app.tools import list_ops as list_tools

logger = logging.getLogger(__name__)


class BatchAgent(BaseAgent):
    name = "batch"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "mark_list_cards_complete":
            return self._mark_list_cards_complete(msg, ins)
        if ask == "archive_list_cards":
            return self._archive_list_cards(msg, ins)
        if ask == "create_cards":
            return self._create_cards(msg, ins)

        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="error",
            data={},
            error=f"Unknown ask={ask!r}",
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _fetch_cards(self, msg: A2AMessage, ins: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]], A2AResponse | None]:
        list_id = str(ins.get("list_id") or "").strip()
        if not list_id:
            return None, [], A2AResponse(
                task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["list_id"]
            )
        st, cards = list_tools.get_list_cards(list_id)
        if st >= 400:
            return list_id, [], A2AResponse(
                task_id=msg.task_id, frm=self.name, status="error", data={},
                error=f"HTTP {st} fetching cards for list {list_id}",
            )
        return list_id, [c for c in cards if isinstance(c, dict)], None

    def _summary_response(self, msg: A2AMessage, list_id: str | None, success: list, errors: list) -> A2AResponse:
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="ok",
            data={
                "list_id": list_id,
                "success_count": len(success),
                "error_count": len(errors),
                "results": success[:50],
                "errors": errors[:20],
            },
        )

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _mark_list_cards_complete(self, msg: A2AMessage, ins: dict[str, Any]) -> A2AResponse:
        list_id, cards, err = self._fetch_cards(msg, ins)
        if err:
            return err

        success, errors = [], []
        for card in cards:
            card_id = card.get("id")
            if not card_id:
                continue
            if card.get("dueComplete"):
                success.append({"id": card_id, "name": card.get("name"), "skipped": True})
                continue
            st, _ = card_tools.set_due_complete(card_id, True)
            if st < 400:
                success.append({"id": card_id, "name": card.get("name")})
            else:
                errors.append({"id": card_id, "name": card.get("name"), "error": f"HTTP {st}"})

        logger.info(
            "[batch] mark_list_cards_complete list_id=%s success=%d errors=%d",
            list_id, len(success), len(errors),
        )
        return self._summary_response(msg, list_id, success, errors)

    def _archive_list_cards(self, msg: A2AMessage, ins: dict[str, Any]) -> A2AResponse:
        list_id, cards, err = self._fetch_cards(msg, ins)
        if err:
            return err

        success, errors = [], []
        for card in cards:
            card_id = card.get("id")
            if not card_id:
                continue
            if card.get("closed"):
                success.append({"id": card_id, "name": card.get("name"), "skipped": True})
                continue
            st, _ = card_tools.set_card_closed(card_id, True)
            if st < 400:
                success.append({"id": card_id, "name": card.get("name")})
            else:
                errors.append({"id": card_id, "name": card.get("name"), "error": f"HTTP {st}"})

        logger.info(
            "[batch] archive_list_cards list_id=%s success=%d errors=%d",
            list_id, len(success), len(errors),
        )
        return self._summary_response(msg, list_id, success, errors)

    def _create_cards(self, msg: A2AMessage, ins: dict[str, Any]) -> A2AResponse:
        list_id = str(ins.get("list_id") or "").strip()
        if not list_id:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["list_id"])

        raw_names = ins.get("names")
        if isinstance(raw_names, str):
            try:
                raw_names = json.loads(raw_names)
            except (json.JSONDecodeError, ValueError):
                raw_names = [n.strip() for n in raw_names.split(",") if n.strip()]
        names = [str(n) for n in (raw_names or []) if n]
        if not names:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["names"])

        success, errors = [], []
        for name in names:
            st, card = card_tools.create_card(list_id, name)
            if st < 400:
                success.append({"name": name, "id": card.get("id")})
            else:
                errors.append({"name": name, "error": f"HTTP {st}"})

        logger.info(
            "[batch] create_cards list_id=%s success=%d errors=%d",
            list_id, len(success), len(errors),
        )
        return self._summary_response(msg, list_id, success, errors)
