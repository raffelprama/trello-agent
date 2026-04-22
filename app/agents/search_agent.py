"""SearchAgent — PRD v3 §6.13."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import search as search_tools


class SearchAgent(BaseAgent):
    name = "search"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "search":
            q = ins.get("query") or ins.get("q")
            if not q:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["query"])
            params: dict[str, Any] = {"query": q}
            if ins.get("modelTypes"):
                params["modelTypes"] = ins["modelTypes"]
            if ins.get("cards_limit"):
                params["cards_limit"] = ins["cards_limit"]
            if ins.get("boards_limit"):
                params["boards_limit"] = ins["boards_limit"]
            if ins.get("partial") is not None:
                params["partial"] = str(ins["partial"]).lower()
            if ins.get("card_fields"):
                params["card_fields"] = ins["card_fields"]
            st, data = search_tools.search_trello(**params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data=dict(data) if isinstance(data, dict) else {"results": data})

        if ask == "search_members":
            q = ins.get("query") or ins.get("q")
            if not q:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["query"])
            st, rows = search_tools.search_members(query=q, limit=ins.get("limit", 20))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"members": rows})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
