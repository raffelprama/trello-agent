"""ChecklistAgent — card checklists, items, state via PUT /cards/{id}/checkItem/{id}."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.utils.resolution import match_dicts_by_name
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

        if ask == "create_checklist":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            name = ins.get("name") or ins.get("checklist_name")
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, ch = card_tools.post_card_checklist(str(card_id), str(name))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"checklist": ch, "checklist_id": ch.get("id") if isinstance(ch, dict) else None},
            )

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
                        data={"checklist_id": ch.get("id"), "checklist": ch, "created": False},
                    )
            # Checklist not found — auto-create so "add item to checklist X" works even when X is new
            st2, ch = card_tools.post_card_checklist(str(card_id), name_hint)
            if st2 >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st2} creating checklist")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"checklist_id": ch.get("id"), "checklist": ch, "created": True},
            )

        if ask == "resolve_check_item":
            checklist_id = ins.get("checklist_id")
            name_hint = str(ins.get("item_name") or ins.get("name") or "").strip()
            if not name_hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["item_name"])

            if not checklist_id:
                if not card_id:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="need_info",
                        data={},
                        missing=["card_id"],
                    )
                st_ch, ch_rows = card_tools.get_card_checklists(str(card_id))
                if st_ch >= 400:
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_ch}")
                flat: list[dict[str, Any]] = []
                for ch in ch_rows or []:
                    if not isinstance(ch, dict):
                        continue
                    cid_ch = ch.get("id")
                    if not cid_ch:
                        continue
                    st_it, items = cl_tools.get_checkitems(str(cid_ch))
                    if st_it >= 400 or not isinstance(items, list):
                        continue
                    for it in items:
                        if isinstance(it, dict) and it.get("id"):
                            flat.append({"checklist_id": str(cid_ch), "check_item_id": it.get("id"), "name": str(it.get("name") or ""), "item": it})
                m = match_dicts_by_name(name_hint, flat)
                if m:
                    it = m.get("item")
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={
                            "check_item_id": m.get("check_item_id"),
                            "checklist_id": m.get("checklist_id"),
                            "item": it if isinstance(it, dict) else m,
                        },
                    )
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"candidates": flat[:50]},
                    clarification="Which check item? No unique match across this card's checklists.",
                )

            st, items = cl_tools.get_checkitems(str(checklist_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            dict_items = [it for it in items if isinstance(it, dict)]
            hit = match_dicts_by_name(name_hint, dict_items)
            if hit:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"check_item_id": hit.get("id"), "item": hit})
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
            want = "complete" if str(state).lower() in ("complete", "true", "1", "yes") else "incomplete"
            if not ins.get("skip_idempotency_check"):
                st_ch, ch_rows = card_tools.get_card_checklists(str(card_id))
                if st_ch < 400 and isinstance(ch_rows, list):
                    found_other_state = False
                    for ch in ch_rows:
                        if not isinstance(ch, dict):
                            continue
                        st_it, items = cl_tools.get_checkitems(str(ch.get("id", "")))
                        if st_it >= 400 or not isinstance(items, list):
                            continue
                        for it in items:
                            if isinstance(it, dict) and str(it.get("id")) == str(ciid):
                                if str(it.get("state", "")).lower() == want:
                                    return A2AResponse(
                                        task_id=msg.task_id,
                                        frm=self.name,
                                        status="ok",
                                        data={"result": it, "skipped": True, "reason": "already_in_state"},
                                    )
                                found_other_state = True
                                break
                        if found_other_state:
                            break
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
