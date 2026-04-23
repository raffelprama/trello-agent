"""OrganizationAgent — PRD v3 §6.12."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import organization as org_tools


class OrganizationAgent(BaseAgent):
    name = "organization"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})

        if ask == "get_my_organizations":
            st, rows = org_tools.get_my_organizations()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"organizations": rows})

        if ask == "get_organization":
            oid = ins.get("org_id") or ins.get("organization_id")
            if not oid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["org_id"])
            st, data = org_tools.get_organization(str(oid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"organization": data})

        if ask == "get_organization_boards":
            oid = ins.get("org_id")
            if not oid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["org_id"])
            st, rows = org_tools.get_organization_boards(str(oid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"boards": rows})

        if ask == "get_organization_members":
            oid = ins.get("org_id")
            if not oid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["org_id"])
            st, rows = org_tools.get_organization_members(str(oid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"members": rows})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
