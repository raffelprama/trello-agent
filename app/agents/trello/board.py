"""BoardAgent — resolve_board (TRELLO_BOARD_ID scope), board CRUD, labels/members/actions."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.core.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.utils.resolution import close_name_matches, match_dicts_by_name
from app.utils.trello_summaries import slim_board, slim_boards
from app.tools import board as board_tools
from app.tools import member as member_tools


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _best_name_match(name_hint: str, boards: list[dict[str, Any]]) -> dict[str, Any] | None:
    return match_dicts_by_name(name_hint, [b for b in boards if isinstance(b, dict)])


def _wants_board_catalog(text: str) -> bool:
    """True when the user is asking to list/show available boards, not to pick one by name."""
    t = _norm(text)
    if not t:
        return False
    # Singular "board" after quantifiers: "all the board", "all my board", "every board"
    if re.search(r"\b(all|every)\s+the\s+boards?\b", t):
        return True
    if re.search(r"\ball\s+my\s+boards?\b", t):
        return True
    if re.search(r"\bevery\s+board\b", t):
        return True
    if re.search(r"\bhow many\s+boards?\b", t):
        return True
    # Verb-led listing (plural boards)
    if re.search(
        r"\b(list|show|display|see|what|which|view|give)\b.*\bboards\b",
        t,
    ):
        return True
    # "see/show all boards" — require plural **boards** so "see all lists under board 'X'"
    # does not match (avoids returning a board catalog instead of resolving board X).
    if re.search(
        r"\b(list|show|display|see|view)\b.*\b(all|every)\b.*\bboards\b",
        t,
    ):
        return True
    if re.search(r"\bboards\b.*\b(available|accessible|there|have)\b", t):
        return True
    if re.search(r"\bboard\b.*\bavailable\b", t):
        return True
    if re.search(r"\b(available|accessible)\b.*\bboards?\b", t):
        return True
    return False


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
            "get_board_summary",
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
            sb = slim_board(b) or {}
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": sb, "board_id": b.get("id")})

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
                        "due": c.get("due"),
                        "dueComplete": c.get("dueComplete"),
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
            sb = slim_board(b) or {}
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": sb, "board_id": b.get("id")})

        if ask == "update_board":
            if not board_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])
            fields = {k: v for k, v in ins.items() if k in ("name", "desc", "closed")}
            st, b = board_tools.update_board(str(board_id), **fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            sb = slim_board(b) or {}
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"board": sb, "board_id": b.get("id")})

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

        if ask == "get_board_summary":
            board_name = mem.get("board_name") or ins.get("board_name") or str(board_id)
            return self._get_board_summary(msg, board_id, board_name)

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

    def _get_board_summary(self, msg: A2AMessage, board_id: Any, board_name: str) -> A2AResponse:
        bid = str(board_id)

        st_l, lists = board_tools.get_board_lists(bid)
        if st_l >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_l} fetching lists")
        list_map: dict[str, str] = {lst["id"]: lst.get("name", "") for lst in lists if isinstance(lst, dict) and lst.get("id")}

        st_m, members = board_tools.get_board_members(bid)
        if st_m >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_m} fetching members")
        member_map: dict[str, str] = {
            m["id"]: m.get("fullName") or m.get("username") or m["id"]
            for m in members if isinstance(m, dict) and m.get("id")
        }

        st_c, raw_cards = board_tools.get_board_cards(bid)
        if st_c >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_c} fetching cards")

        now_utc = datetime.now(timezone.utc)
        soon = now_utc + timedelta(days=7)
        very_soon = now_utc + timedelta(days=3)

        def _parse_due(due_str: str | None) -> datetime | None:
            if not due_str:
                return None
            try:
                return datetime.fromisoformat(due_str.replace("Z", "+00:00"))
            except ValueError:
                return None

        cards = [c for c in raw_cards if isinstance(c, dict)]
        total = len(cards)

        completed: list[dict] = []
        incomplete: list[dict] = []
        overdue: list[dict] = []
        upcoming_7: list[dict] = []
        upcoming_3: list[dict] = []

        by_list: dict[str, dict] = {}
        by_member: dict[str, dict] = {}

        for c in cards:
            done = bool(c.get("dueComplete"))
            due_dt = _parse_due(c.get("due"))
            list_id = c.get("idList") or ""
            list_name = list_map.get(list_id, "Unknown")
            card_ids = c.get("idMembers") or []

            slim = {"name": c.get("name"), "due": c.get("due"), "list_name": list_name}

            if done:
                completed.append(slim)
            else:
                incomplete.append(slim)
                if due_dt and due_dt < now_utc:
                    overdue.append(slim)
                elif due_dt and due_dt <= soon:
                    upcoming_7.append(slim)
                    if due_dt <= very_soon:
                        upcoming_3.append(slim)

            # Per-list
            if list_name not in by_list:
                by_list[list_name] = {"list_name": list_name, "total": 0, "completed": 0, "incomplete": 0}
            by_list[list_name]["total"] += 1
            if done:
                by_list[list_name]["completed"] += 1
            else:
                by_list[list_name]["incomplete"] += 1

            # Per-member
            if not card_ids:
                mn = "Unassigned"
                if mn not in by_member:
                    by_member[mn] = {"member": mn, "total": 0, "completed": 0, "incomplete": 0, "overdue": 0}
                by_member[mn]["total"] += 1
                by_member[mn]["completed" if done else "incomplete"] += 1
                if not done and due_dt and due_dt < now_utc:
                    by_member[mn]["overdue"] += 1
            else:
                for mid in card_ids:
                    mn = member_map.get(mid, mid)
                    if mn not in by_member:
                        by_member[mn] = {"member": mn, "total": 0, "completed": 0, "incomplete": 0, "overdue": 0}
                    by_member[mn]["total"] += 1
                    by_member[mn]["completed" if done else "incomplete"] += 1
                    if not done and due_dt and due_dt < now_utc:
                        by_member[mn]["overdue"] += 1

        completion_pct = round(len(completed) / total * 100, 1) if total else 0.0
        incomplete_count = len(incomplete)
        unassigned_incomplete = by_member.get("Unassigned", {}).get("incomplete", 0)

        # Recommendations
        recs: list[str] = []
        if overdue:
            recs.append(f"{len(overdue)} card(s) are overdue — address these immediately.")
        if upcoming_3:
            recs.append(f"{len(upcoming_3)} card(s) are due within the next 3 days.")
        if completion_pct < 30 and total >= 5:
            recs.append(f"Only {completion_pct}% of cards are completed — consider reviewing scope or re-prioritizing.")
        if incomplete_count > 0 and unassigned_incomplete / incomplete_count > 0.3:
            recs.append(f"{unassigned_incomplete} incomplete card(s) have no member assigned.")
        if by_member:
            heaviest = max(
                ((m, d) for m, d in by_member.items() if m != "Unassigned"),
                key=lambda x: x[1]["incomplete"],
                default=(None, None),
            )
            if heaviest[0] and incomplete_count > 0 and heaviest[1]["incomplete"] / incomplete_count > 0.5:
                recs.append(
                    f"{heaviest[0]} holds {heaviest[1]['incomplete']} of {incomplete_count} incomplete cards — consider rebalancing."
                )

        summary = {
            "board_name": board_name,
            "total_cards": total,
            "completed_count": len(completed),
            "incomplete_count": incomplete_count,
            "completion_pct": completion_pct,
            "overdue_count": len(overdue),
            "overdue": overdue[:10],
            "upcoming_due_7_days": upcoming_7[:10],
            "by_list": sorted(by_list.values(), key=lambda x: x["total"], reverse=True),
            "by_member": sorted(by_member.values(), key=lambda x: x["total"], reverse=True),
            "recommendations": recs,
        }
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="ok",
            data={"board_summary": summary, "board_id": board_id, "resolved_board_name": board_name},
        )

    def _resolve_board(self, msg: A2AMessage, ins: dict[str, Any], mem: dict[str, Any]) -> A2AResponse:
        hint = ins.get("board_hint") or ins.get("name") or ""
        uid_text = (msg.context or {}).get("user_text") or ""

        # Env-scoped default board
        if TRELLO_BOARD_ID and BOARD_SCOPE_ONLY:
            st, b = board_tools.get_board(TRELLO_BOARD_ID)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st} loading default board")
            sb = slim_board(b) or {}
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "board_id": b.get("id"),
                    "board": sb,
                    "resolved_board_name": b.get("name"),
                },
            )

        hint_clean = str(hint or "").strip()
        bid_in = ins.get("board_id")
        # Plan executor often inserts resolve_board with board_id from a prior step but no hint; accept a valid id.
        if bid_in and not hint_clean:
            st_b, b_direct = board_tools.get_board(str(bid_in))
            if st_b < 400 and isinstance(b_direct, dict):
                sb = slim_board(b_direct) or {}
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={
                        "board_id": b_direct.get("id"),
                        "board": sb,
                        "resolved_board_name": b_direct.get("name"),
                    },
                )

        if mem.get("board_id") and not hint_clean:
            st, b = board_tools.get_board(str(mem["board_id"]))
            if st < 400 and isinstance(b, dict):
                sb = slim_board(b) or {}
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"board_id": b.get("id"), "board": sb, "resolved_board_name": b.get("name")},
                )

        st, boards = member_tools.get_my_boards()
        if st >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st} listing boards")

        # List / "what's available" questions — return all boards, not a disambiguation prompt.
        if _wants_board_catalog(uid_text) or _wants_board_catalog(hint_clean):
            summary = slim_boards([b for b in boards if isinstance(b, dict)])
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"boards": summary, "board_count": len(summary)},
            )

        # Prefer hint from inputs; else extract a board name from user_text (avoid greedy "board …" matches).
        name_guess = hint_clean if hint_clean else ""
        if not name_guess and uid_text:
            m = re.search(r"board\s+[\"']([^\"'\n]+)[\"']", uid_text, re.I)
            if m:
                name_guess = m.group(1).strip()
            else:
                m2 = re.search(
                    r"\b(?:on\s+)?(?:the\s+)?board\s+(?:called|named)\s+[\"']?([^\"'\n,?.!]+)",
                    uid_text,
                    re.I,
                )
                if m2:
                    name_guess = m2.group(1).strip()

        if not name_guess:
            if len(boards) == 1:
                b = boards[0]
                sb = slim_board(b) if isinstance(b, dict) else {}
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"board_id": b.get("id"), "board": sb, "resolved_board_name": b.get("name")},
                )
            cand = [{"id": b.get("id"), "name": b.get("name")} for b in boards[:30] if isinstance(b, dict)]
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"candidates": cand},
                clarification="Which board do you mean? " + ", ".join(f"{c.get('name')}" for c in cand[:8] if c.get("name")),
            )

        board_dicts = [b for b in boards if isinstance(b, dict)]
        match = _best_name_match(name_guess, board_dicts)
        if match:
            sm = slim_board(match) or {}
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={
                    "board_id": match.get("id"),
                    "board": sm,
                    "resolved_board_name": match.get("name"),
                },
            )

        close = close_name_matches(
            name_guess,
            board_dicts,
            get_name=lambda b: str(b.get("name", "")),
            max_levenshtein=2,
            max_results=8,
        )
        if close:
            cand = [{"id": b.get("id"), "name": b.get("name")} for b in close if b.get("id")]
            names = ", ".join(str(c.get("name")) for c in cand if c.get("name"))
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"candidates": cand, "hint": name_guess},
                clarification=(
                    f"No exact match for {name_guess!r}. Did you mean one of these boards? {names} "
                    "(reply with the board name.)"
                ),
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
