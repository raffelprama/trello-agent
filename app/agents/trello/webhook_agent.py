"""WebhookAgent — PRD v3 §6.11."""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import webhook as wh_tools


class WebhookAgent(BaseAgent):
    name = "webhook"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "list_webhooks":
            st, rows = wh_tools.list_webhooks()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"webhooks": rows})

        if ask == "create_webhook":
            raw = ins.get("body_json") or "{}"
            try:
                body = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except json.JSONDecodeError:
                body = {
                    "description": ins.get("description") or "",
                    "callbackURL": ins.get("callbackURL") or ins.get("callback_url"),
                    "idModel": ins.get("idModel") or ins.get("id_model"),
                    "active": ins.get("active", True),
                }
            if not body.get("callbackURL") or not body.get("idModel"):
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["callbackURL", "idModel"])
            st, data = wh_tools.create_webhook(body)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"webhook": data})

        if ask == "delete_webhook":
            wid = ins.get("webhook_id")
            if not wid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["webhook_id"])
            st, _ = wh_tools.delete_webhook(str(wid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        if ask == "get_webhook":
            wid = ins.get("webhook_id")
            if not wid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["webhook_id"])
            st, data = wh_tools.get_webhook(str(wid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"webhook": data})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
