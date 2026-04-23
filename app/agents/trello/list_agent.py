"""ListAgent — resolve_list, list cards, CRUD. Uses BoardAgent via bus if board_id missing."""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent, new_task_id
from app.utils.resolution import match_dicts_by_name
from app.tools import board as board_tools
from app.tools import list_ops as list_tools


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _best_list_match(name_hint: str, lists: list[dict[str, Any]]) -> dict[str, Any] | None:
    return match_dicts_by_name(name_hint, [x for x in lists if isinstance(x, dict)])


class ListAgent(BaseAgent):
    name = "list"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        mem = (msg.context or {}).get("memory") or {}
        ctx = msg.context or {}

        board_id = ins.get("board_id") or mem.get("board_id")

        if ask in (
            "resolve_list",
            "get_list_cards",
            "create_list",
            "update_list",
            "archive_list",
            "set_list_closed",
            "set_list_pos",
        ) and not board_id:
            if self.bus and ask == "resolve_list":
                sub = A2AMessage(
                    task_id=new_task_id(),
                    frm=self.name,
                    to="board",
                    ask="resolve_board",
                    context={**ctx, "_resolved_inputs": {k: ins[k] for k in ("board_hint", "name") if k in ins}},
                )
                br = self.bus.dispatch(sub)
                if br.status != "ok":
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status=br.status, data=br.data, missing=br.missing, clarification=br.clarification, error=br.error)
                board_id = br.data.get("board_id")
                ins = {**ins, "board_id": board_id}
            else:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])

        board_id = ins.get("board_id") or mem.get("board_id")

        if ask == "resolve_list":
            return self._resolve_list(msg, ins, mem)

        list_id = ins.get("list_id")
        if ask in ("get_list_cards", "update_list", "archive_list", "set_list_closed", "set_list_pos") and not list_id:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["list_id"])

        if ask == "get_list_cards":
            fields = ins.get("fields")
            params: dict[str, Any] = {}
            if fields:
                params["fields"] = fields
            st, cards = list_tools.get_list_cards(str(list_id), **params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            out = [
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "due": c.get("due"),
                    "dueComplete": c.get("dueComplete"),
                }
                for c in cards
                if isinstance(c, dict)
            ]
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"cards": out, "list_id": list_id},
            )

        if ask == "create_list":
            name = ins.get("name") or ins.get("list_name")
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, lst = list_tools.create_list(str(board_id), str(name), pos=ins.get("pos"))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"list": lst, "list_id": lst.get("id")})

        if ask == "update_list":
            fields = {k: v for k, v in ins.items() if k in ("name", "pos", "closed")}
            st, lst = list_tools.update_list(str(list_id), **fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"list": lst, "list_id": lst.get("id")})

        if ask == "archive_list":
            closed = bool(ins.get("closed", True))
            st, lst = list_tools.archive_list(str(list_id), closed=closed)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"list": lst, "list_id": list_id})

        if ask == "set_list_closed":
            val = ins.get("closed")
            if val is None:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["closed"])
            st, lst = list_tools.set_list_closed(str(list_id), bool(val))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"list": lst, "list_id": list_id})

        if ask == "set_list_pos":
            pos = ins.get("pos")
            if pos is None:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["pos"])
            st, lst = list_tools.set_list_pos(str(list_id), pos)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"list": lst, "list_id": list_id})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")

    def _resolve_list(self, msg: A2AMessage, ins: dict[str, Any], mem: dict[str, Any]) -> A2AResponse:
        board_id = ins.get("board_id")
        hint = ins.get("list_hint") or ins.get("name") or ins.get("list_name") or ""
        uid = (msg.context or {}).get("user_text") or ""

        st, lists = board_tools.get_board_lists(str(board_id), cards="none")
        if st >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")

        if not hint:
            m = re.search(r"list\s+[\"']?([^\"'\n]+)[\"']?", uid, re.I)
            if m:
                hint = m.group(1).strip()

        list_map = mem.get("list_map") or []
        if isinstance(list_map, list) and hint:
            for row in list_map:
                if isinstance(row, dict) and _norm(str(row.get("name", ""))) == _norm(hint):
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={"list_id": row.get("id"), "list_name": row.get("name"), "resolved_list_name": row.get("name")},
                    )

        match = _best_list_match(str(hint), [x for x in lists if isinstance(x, dict)])
        if match:
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "list_id": match.get("id"),
                    "list_name": match.get("name"),
                    "resolved_list_name": match.get("name"),
                },
            )

        cand = [{"id": x.get("id"), "name": x.get("name")} for x in lists if isinstance(x, dict)]
        if len(cand) > 10:
            cand = cand[:10]
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="clarify_user",
            data={"candidates": cand, "hint": hint},
            clarification="Which list? Options: " + ", ".join(str(c.get("name")) for c in cand if c.get("name")),
        )
