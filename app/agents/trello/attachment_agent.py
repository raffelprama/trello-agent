"""AttachmentAgent — URL attachments on cards (PRD v3 §6.9)."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import attachment as att_tools


class AttachmentAgent(BaseAgent):
    name = "attachment"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        cid = ins.get("card_id")

        if ask == "list_attachments":
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, rows = att_tools.list_attachments(str(cid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"attachments": rows, "card_id": cid})

        if ask == "add_url_attachment":
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            url = ins.get("url")
            if not url:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["url"])
            st, data = att_tools.add_url_attachment(str(cid), str(url), name=ins.get("name"), mime_type=ins.get("mimeType"))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"attachment": data})

        if ask == "delete_attachment":
            aid = ins.get("attachment_id")
            if not cid or not aid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id", "attachment_id"])
            st, _ = att_tools.delete_attachment(str(cid), str(aid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
