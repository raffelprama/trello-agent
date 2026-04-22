"""BoardAgent — resolve_board (TRELLO_BOARD_ID scope), board CRUD, labels/members/actions."""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.resolution import match_dicts_by_name
from app.tools import board as board_tools
from app.tools import member as member_tools


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _best_name_match(name_hint: str, boards: list[dict[str, Any]]) -> dict[str, Any] | None:
    return match_dicts_by_name(name_hint, [b for b in boards if isinstance(b, dict)])


class BoardAgent(BaseAgent):
    name = "board"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        mem = (msg.context or {}).get("memory") or {}

        if ask == "resolve_board":
            return self._resolve_board(msg, ins, mem)

        board_id = ins.get("board_id") or mem.get("board_id")
        if ask in (
            "get_board",
            "get_board_lists",
            "get_board_labels",
            "get_board_members",
            "get_board_actions",
            "get_board_cards",
            "get_board_custom_fields",
            "delete_board",
            "add_board_member",
            "remove_board_member",
            "get_board_memberships",
        ) and not board_id:
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="need_info",
                data={},
                missing=["board_id"],
            )

        if ask == "get_board":
            st, b = board_tools.get_board(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": b, "board_id": b.get("id")})

        if ask == "get_board_lists":
            cards = str(ins.get("cards") or "none")
            fields = ins.get("fields")
            st, lists = board_tools.get_board_lists(str(board_id), cards=cards, fields=fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"lists": lists, "board_id": board_id},
            )

        if ask == "get_board_cards":
            mem_ctx = (msg.context or {}).get("memory") or {}
            st, cards = board_tools.get_board_cards(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            out_cards: list[dict[str, Any]] = []
            for c in cards:
                if not isinstance(c, dict):
                    continue
                lid = c.get("idList")
                lname = None
                # idList only on card; list name requires join — leave list as id or fetch later
                out_cards.append(
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "list": lname,
                        "idList": lid,
                    }
                )
            qb_name = mem_ctx.get("board_name")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "cards": out_cards,
                    "queried_board": {"id": board_id, "name": qb_name},
                    "board_id": board_id,
                    "resolved_board_name": qb_name,
                },
            )

        if ask == "get_board_labels":
            st, labels = board_tools.get_board_labels(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"labels": labels, "board_id": board_id})

        if ask == "get_board_members":
            st, members = board_tools.get_board_members(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"members": members, "board_id": board_id})

        if ask == "get_board_actions":
            st, actions = board_tools.get_board_actions(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"actions": actions, "board_id": board_id})

        if ask == "create_board":
            name = ins.get("name")
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, b = board_tools.create_board(str(name), desc=ins.get("desc"))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": b, "board_id": b.get("id")})

        if ask == "update_board":
            if not board_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            fields = {k: v for k, v in ins.items() if k in ("name", "desc", "closed")}
            st, b = board_tools.update_board(str(board_id), **fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": b, "board_id": b.get("id")})

        if ask == "get_board_custom_fields":
            params = {k: v for k, v in ins.items() if k in ("fields",)}
            st, cfs = board_tools.get_board_custom_fields(str(board_id), **params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_fields": cfs, "board_id": board_id})

        if ask == "get_board_memberships":
            params = {k: v for k, v in ins.items() if k in ("fields", "filter", "member", "organization")}
            st, mships = board_tools.get_board_memberships(str(board_id), **params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"memberships": mships, "board_id": board_id})

        if ask == "add_board_member":
            mid = ins.get("member_id") or ins.get("idMember")
            if not mid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["member_id"])
            mtype = str(ins.get("type") or ins.get("member_type") or "normal")
            st, out = board_tools.add_board_member(str(board_id), str(mid), member_type=mtype)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"membership": out, "board_id": board_id})

        if ask == "remove_board_member":
            mid = ins.get("member_id") or ins.get("idMember")
            if not mid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["member_id"])
            st, _ = board_tools.remove_board_member(str(board_id), str(mid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"removed": True, "board_id": board_id, "member_id": mid})

        if ask == "delete_board":
            st, _ = board_tools.delete_board(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True, "board_id": board_id})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")

    def _resolve_board(self, msg: A2AMessage, ins: dict[str, Any], mem: dict[str, Any]) -> A2AResponse:
        hint = ins.get("board_hint") or ins.get("name") or ""
        uid_text = (msg.context or {}).get("user_text") or ""

        # Env-scoped default board
        if TRELLO_BOARD_ID and BOARD_SCOPE_ONLY:
            st, b = board_tools.get_board(TRELLO_BOARD_ID)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st} loading default board")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "board_id": b.get("id"),
                    "board": b,
                    "resolved_board_name": b.get("name"),
                },
            )

        hint_clean = str(hint or "").strip()
        bid_in = ins.get("board_id")
        # Plan executor often inserts resolve_board with board_id from a prior step but no hint; accept a valid id.
        if bid_in and not hint_clean:
            st_b, b_direct = board_tools.get_board(str(bid_in))
            if st_b < 400 and isinstance(b_direct, dict):
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={
                        "board_id": b_direct.get("id"),
                        "board": b_direct,
                        "resolved_board_name": b_direct.get("name"),
                    },
                )

        if mem.get("board_id") and not hint_clean:
            st, b = board_tools.get_board(str(mem["board_id"]))
            if st < 400 and isinstance(b, dict):
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"board_id": b.get("id"), "board": b, "resolved_board_name": b.get("name")},
                )

        st, boards = member_tools.get_my_boards()
        if st >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st} listing boards")

        # Prefer hint from inputs; else try extract quoted name from user_text
        name_guess = hint_clean if hint_clean else ""
        if not name_guess and uid_text:
            m = re.search(r"board\s+[\"']?([^\"'\n]+)[\"']?", uid_text, re.I)
            if m:
                name_guess = m.group(1).strip()

        if not name_guess:
            if len(boards) == 1:
                b = boards[0]
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"board_id": b.get("id"), "board": b, "resolved_board_name": b.get("name")},
                )
            cand = [{"id": b.get("id"), "name": b.get("name")} for b in boards[:30] if isinstance(b, dict)]
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"candidates": cand},
                clarification="Which board do you mean? " + ", ".join(f"{c.get('name')}" for c in cand[:8] if c.get("name")),
            )

        match = _best_name_match(name_guess, [b for b in boards if isinstance(b, dict)])
        if match:
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "board_id": match.get("id"),
                    "board": match,
                    "resolved_board_name": match.get("name"),
                },
            )

        cand = [{"id": b.get("id"), "name": b.get("name")} for b in boards[:30] if isinstance(b, dict)]
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="clarify_user",
            data={"candidates": cand, "hint": name_guess},
            clarification=f"I couldn't find a board matching {name_guess!r}. Which one? Options: "
            + ", ".join(str(c.get("name")) for c in cand[:10] if c.get("name")),
        )
