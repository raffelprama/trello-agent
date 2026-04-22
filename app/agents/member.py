"""MemberAgent — /members/me, boards, cards."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import member as member_tools


class MemberAgent(BaseAgent):
    name = "member"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ctx = dict(msg.context or {})
        if ask == "get_me":
            st, data = member_tools.get_me()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"member": data})

        if ask == "get_my_boards":
            st, boards = member_tools.get_my_boards()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"boards": boards})

        if ask == "get_member_cards":
            ri = ctx.get("_resolved_inputs") or {}
            if not isinstance(ri, dict):
                ri = {}
            mid = ri.get("member_id") or "me"
            params = {k: v for k, v in ri.items() if k in ("filter", "fields")}
            st, cards = member_tools.get_member_cards(str(mid), **params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"cards": cards})

        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="error",
            data={},
            error=f"Unknown ask={ask!r}",
        )
