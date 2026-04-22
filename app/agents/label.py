"""LabelAgent — resolve label on board, add/remove on card, create on board."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.resolution import match_dicts_by_name
from app.tools import board as board_tools
from app.tools import card as card_tools
from app.tools import label as label_tools


class LabelAgent(BaseAgent):
    name = "label"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        mem = (msg.context or {}).get("memory") or {}
        board_id = ins.get("board_id") or mem.get("board_id")
        card_id = ins.get("card_id")

        if ask == "resolve_label":
            if not board_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            hint = str(ins.get("label_name") or ins.get("name") or "").strip()
            st, labels = board_tools.get_board_labels(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            if not hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["label_name"])
            dict_labels = [lb for lb in labels if isinstance(lb, dict)]
            hit = match_dicts_by_name(hint, dict_labels, name_key="name")
            if hit:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"label_id": hit.get("id"), "label": hit})
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"labels": labels},
                clarification="Which label? " + ", ".join(str(x.get("name")) for x in labels if isinstance(x, dict))[:240],
            )

        if ask == "add_label_to_card":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            lid = ins.get("label_id")
            if not lid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["label_id"])
            st, _ = card_tools.add_label(str(card_id), str(lid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"ok": True, "card_id": card_id})

        if ask == "remove_label_from_card":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            lid = ins.get("label_id")
            if not lid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["label_id"])
            st, _ = card_tools.remove_label(str(card_id), str(lid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"ok": True})

        if ask == "create_label_on_board":
            if not board_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            name = ins.get("name") or ins.get("label_name")
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, lb = board_tools.create_label(str(board_id), str(name), color=ins.get("color"))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"label": lb, "label_id": lb.get("id")})

        if ask == "get_label":
            lid = ins.get("label_id")
            if not lid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["label_id"])
            st, lb = label_tools.get_label(str(lid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"label": lb})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
