"""CustomFieldAgent — board definitions and card values (PRD v3 §6.10)."""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import custom_field as cf_tools


class CustomFieldAgent(BaseAgent):
    name = "custom_field"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "get_board_custom_fields":
            bid = ins.get("board_id")
            if not bid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            st, rows = cf_tools.get_board_custom_fields(str(bid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_fields": rows, "board_id": bid})

        if ask == "create_custom_field":
            bid = ins.get("board_id")
            raw = ins.get("definition_json") or ins.get("body_json") or "{}"
            try:
                body = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                body = {"name": ins.get("name"), "type": ins.get("type") or "text"}
            if not bid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            st, data = cf_tools.create_custom_field(str(bid), body)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_field": data})

        if ask == "get_card_custom_field_items":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, rows = cf_tools.get_card_custom_field_items(str(cid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_field_items": rows, "card_id": cid})

        if ask == "set_card_custom_field_value":
            cid = ins.get("card_id")
            cfid = ins.get("custom_field_id")
            raw = ins.get("value_json") or "{}"
            if not cid or not cfid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id", "custom_field_id"])
            try:
                body = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                body = {"value": {"text": str(raw)}}
            st, data = cf_tools.set_card_custom_field_item(str(cid), str(cfid), body)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"result": data})

        if ask == "delete_custom_field":
            cfid = ins.get("custom_field_id")
            if not cfid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["custom_field_id"])
            st, _ = cf_tools.delete_custom_field(str(cfid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
