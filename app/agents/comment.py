"""CommentAgent — list/create/update/delete card comments (actions)."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import action as action_tools


class CommentAgent(BaseAgent):
    name = "comment"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        card_id = ins.get("card_id")

        if ask == "list_comments":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, actions = action_tools.get_card_actions(str(card_id), filter="commentCard")
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            comments: list[dict[str, Any]] = []
            for a in actions:
                if not isinstance(a, dict):
                    continue
                if a.get("type") == "commentCard":
                    comments.append(a)
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"comments": comments, "card_id": card_id})

        if ask == "create_comment":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            text = ins.get("text")
            if not text:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["text"])
            st, data = action_tools.post_comment(str(card_id), str(text))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"action": data})

        if ask == "update_comment":
            action_id = ins.get("action_id") or ins.get("comment_id")
            text = ins.get("text")
            if not action_id or not text:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["action_id", "text"])
            st, data = action_tools.update_comment(str(action_id), str(text))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"action": data})

        if ask == "delete_comment":
            action_id = ins.get("action_id") or ins.get("comment_id")
            if not action_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["action_id"])
            st, _ = action_tools.delete_comment(str(action_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
