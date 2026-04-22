"""NotificationAgent — PRD v3 §6.14."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import notification as notif_tools


class NotificationAgent(BaseAgent):
    name = "notification"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "list_notifications":
            params = {k: v for k, v in ins.items() if k in ("filter", "read_filter", "limit", "page")}
            st, rows = notif_tools.get_my_notifications(**params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"notifications": rows})

        if ask == "mark_all_notifications_read":
            st, _ = notif_tools.mark_all_notifications_read()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"ok": True})

        if ask == "update_notification":
            nid = ins.get("notification_id")
            if not nid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["notification_id"])
            fields = {k: v for k, v in ins.items() if k in ("unread",)}
            st, data = notif_tools.update_notification(str(nid), **fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"notification": data})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
