"""ChecklistAgent — card checklists, items, state via PUT /cards/{id}/checkItem/{id}."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import card as card_tools
from app.tools import checklist as cl_tools


class ChecklistAgent(BaseAgent):
    name = "checklist"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        card_id = ins.get("card_id")

        if ask == "list_checklists":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, rows = card_tools.get_card_checklists(str(card_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"checklists": rows, "card_id": card_id})

        if ask == "resolve_checklist":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            name_hint = str(ins.get("checklist_name") or ins.get("name") or "").strip()
            st, rows = card_tools.get_card_checklists(str(card_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            if not name_hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_name"])
            low = name_hint.lower()
            for ch in rows:
                if isinstance(ch, dict) and low in str(ch.get("name", "")).lower():
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={"checklist_id": ch.get("id"), "checklist": ch},
                    )
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"checklists": rows},
                clarification="Which checklist? Available: " + ", ".join(str(c.get("name")) for c in rows if isinstance(c, dict))[:300],
            )

        if ask == "resolve_check_item":
            checklist_id = ins.get("checklist_id")
            name_hint = str(ins.get("item_name") or ins.get("name") or "").strip()
            if not checklist_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_id"])
            st, items = cl_tools.get_checkitems(str(checklist_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            if not name_hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["item_name"])
            low = name_hint.lower()
            for it in items:
                if isinstance(it, dict) and low in str(it.get("name", "")).lower():
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"check_item_id": it.get("id"), "item": it})
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"items": items},
                clarification="Which check item?",
            )

        if ask == "set_checkitem_state":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            ciid = ins.get("check_item_id")
            state = ins.get("state") or "complete"
            if not ciid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["check_item_id"])
            st, data = cl_tools.set_checkitem_state(str(card_id), str(ciid), str(state))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"result": data})

        if ask == "create_checkitem":
            checklist_id = ins.get("checklist_id")
            name = ins.get("name") or ins.get("item_name")
            if not checklist_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_id"])
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, data = cl_tools.create_checkitem(str(checklist_id), str(name))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"checkItem": data})

        if ask == "delete_checkitem":
            checklist_id = ins.get("checklist_id")
            ciid = ins.get("check_item_id")
            if not checklist_id or not ciid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_id", "check_item_id"])
            st, data = cl_tools.delete_checkitem(str(checklist_id), str(ciid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
