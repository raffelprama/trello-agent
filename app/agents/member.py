"""MemberAgent — /members/me, boards, cards."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.resolution import best_match_by_name, levenshtein, match_dicts_by_name
from app.tools import board as board_tools
from app.tools import member as member_tools


def _member_search_blob(m: dict[str, Any]) -> str:
    fn = str(m.get("fullName") or "").strip()
    un = str(m.get("username") or "").strip()
    return " ".join(p for p in (fn, un) if p)


class MemberAgent(BaseAgent):
    name = "member"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ctx = dict(msg.context or {})
        if ask == "resolve_member":
            ri = dict((msg.context or {}).get("_resolved_inputs") or {})
            board_id = ri.get("board_id")
            hint = str(ri.get("member_hint") or ri.get("name") or ri.get("fullName") or "").strip()
            if not board_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            if not hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["member_hint"])
            st, rows = board_tools.get_board_members(str(board_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            dicts = [m for m in rows if isinstance(m, dict)]
            hit = match_dicts_by_name(hint, dicts, name_key="fullName")
            if not hit:
                hit = match_dicts_by_name(hint, dicts, name_key="username")
            if not hit:
                token_rows: list[dict[str, Any]] = []
                for m in dicts:
                    fn = str(m.get("fullName") or "").strip()
                    tok = fn.split()[0] if fn else ""
                    if tok:
                        token_rows.append({**m, "name": tok})
                hit = match_dicts_by_name(hint, token_rows, name_key="name")
            if not hit:
                hit = best_match_by_name(hint, dicts, get_name=_member_search_blob)
            if hit:
                mid = hit.get("id")
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={
                        "member_id": mid,
                        "member_name": hit.get("fullName"),
                        "username": hit.get("username"),
                    },
                )
            nh = " ".join(hint.strip().lower().split())
            scored: list[tuple[int, dict[str, Any]]] = []
            for m in dicts:
                fn = str(m.get("fullName") or "").strip().lower()
                un = str(m.get("username") or "").strip().lower()
                best = 999
                for cand in (fn, un):
                    if not cand:
                        continue
                    if cand == nh:
                        best = min(best, 0)
                    elif cand.startswith(nh):
                        best = min(best, 1)
                    elif nh in cand:
                        best = min(best, 2)
                    else:
                        lev = levenshtein(nh, cand)
                        if lev <= 2:
                            best = min(best, 3 + lev)
                if best <= 5:
                    scored.append((best, m))
            scored.sort(key=lambda t: t[0])
            top = [m for _, m in scored[:6]] if scored else dicts[:6]
            labels = ", ".join(_member_search_blob(x) or str(x.get("id")) for x in top if isinstance(x, dict))
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"candidates": top},
                clarification=("Which member? " + labels[:300]) if labels else "Which member?",
            )

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

        if ask == "get_my_notifications":
            params = {k: v for k, v in ctx.get("_resolved_inputs", {}).items() if k in ("filter", "read_filter", "limit", "page")}
            st, rows = member_tools.get_my_notifications(**params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"notifications": rows})

        if ask == "get_my_organizations":
            st, rows = member_tools.get_my_organizations()
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"organizations": rows})

        if ask == "update_me":
            ri = ctx.get("_resolved_inputs") or {}
            fields = {k: v for k, v in ri.items() if k in ("fullName", "bio")}
            if not fields:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["fullName", "bio"])
            st, data = member_tools.update_me(**fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"member": data})

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
