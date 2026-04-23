"""CardAgent — resolve_card (last_cards), card CRUD, move."""

from __future__ import annotations

import re
from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent, new_task_id
from app.core.config import DELETE_ITEM
from app.tools import board as board_tools
from app.tools import card as card_tools


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _card_name_matches_hint(name_hint: str, card_name: str) -> bool:
    """
    Match card title to user hint without substring hits inside unrelated words
    (e.g. hint 'Ai' must not match 'TEST_AGAIN' via the 'ai' inside 'again').
    """
    nh = _norm(name_hint)
    cn = _norm(card_name)
    if not nh:
        return False
    if not cn:
        return False
    if cn == nh:
        return True
    if len(nh) < 2:
        return False
    if cn.startswith(nh):
        return True
    try:
        pat = r"(?i)(?<![a-z0-9])" + re.escape(nh) + r"(?![a-z0-9])"
        if re.search(pat, cn):
            return True
    except re.error:
        pass
    return False


def _match_cards(name_hint: str, lists_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nh = _norm(name_hint)
    if not nh:
        return []
    matches: list[dict[str, Any]] = []
    for lst in lists_payload:
        if not isinstance(lst, dict):
            continue
        lname = lst.get("name")
        for c in lst.get("cards") or []:
            if not isinstance(c, dict):
                continue
            cn = str(c.get("name") or "")
            if _card_name_matches_hint(name_hint, cn):
                matches.append(
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "list": lname,
                        "idList": c.get("idList"),
                    }
                )
    return matches


class CardAgent(BaseAgent):
    name = "card"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        mem = (msg.context or {}).get("memory") or {}
        ctx = msg.context or {}

        if ask == "resolve_card":
            return self._resolve_card(msg, ins, mem)

        if ask == "get_card_details":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, card = card_tools.get_card_details(str(cid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            lst = card.get("idList")
            lname = None
            if isinstance(lst, str):
                # fetch list name
                st2, lst_obj = board_tools.get_board_lists(str(card.get("idBoard")), cards="none")
                if st2 < 400 and isinstance(lst_obj, list):
                    for L in lst_obj:
                        if isinstance(L, dict) and L.get("id") == lst:
                            lname = L.get("name")
                            break
            enriched = dict(card)
            if lname:
                enriched["list"] = {"name": lname}
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"card": enriched, "card_id": cid},
            )

        board_id = ins.get("board_id") or mem.get("board_id")
        if ask == "create_card":
            list_id = ins.get("list_id")
            name = ins.get("card_name") or ins.get("name")
            if not list_id and self.bus:
                sub = A2AMessage(
                    task_id=new_task_id(),
                    frm=self.name,
                    to="list",
                    ask="resolve_list",
                    context={**ctx, "_resolved_inputs": {**ins, "board_id": board_id}},
                )
                lr = self.bus.dispatch(sub)
                if lr.status != "ok":
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status=lr.status, data=lr.data, missing=lr.missing, clarification=lr.clarification, error=lr.error)
                list_id = lr.data.get("list_id")
                ins = {**ins, "list_id": list_id}
            if not name:
                # continuation / short reply
                name = self._extract_card_title((msg.context or {}).get("user_text") or "")
            if not list_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["list_id"])
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_name"])
            st, c = card_tools.create_card(str(list_id), str(name), desc=ins.get("desc"), due=ins.get("due"))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": c.get("id")})

        if ask == "update_card":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            allowed = (
                "name",
                "desc",
                "due",
                "dueComplete",
                "closed",
                "idList",
                "idBoard",
                "pos",
                "start",
                "idMembers",
                "idLabels",
                "address",
                "locationName",
                "coordinates",
            )
            fields = {k: v for k, v in ins.items() if k in allowed}
            st, c = card_tools.update_card(str(cid), **fields)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": c.get("id")})

        if ask == "move_card":
            cid = ins.get("card_id")
            target = ins.get("target_list_id") or ins.get("idList")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            if not target:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["target_list_id"])
            if not ins.get("skip_idempotency_check"):
                st0, cur = card_tools.get_card_details(str(cid))
                if st0 < 400 and isinstance(cur, dict) and str(cur.get("idList") or "") == str(target):
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={"card": cur, "card_id": cid, "skipped": True, "reason": "already_on_list"},
                    )
            st, c = card_tools.move_card(str(cid), str(target))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": c.get("id")})

        if ask == "delete_card":
            if not DELETE_ITEM:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="error",
                    data={},
                    error="Delete is disabled (set DELETE_ITEM=true in .env).",
                )
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, _ = card_tools.delete_card(str(cid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True, "card_id": cid})

        if ask == "set_card_closed":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            closed = ins.get("closed")
            if closed is None:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["closed"])
            want = bool(closed)
            if not ins.get("skip_idempotency_check"):
                st0, cur = card_tools.get_card_details(str(cid))
                if st0 < 400 and isinstance(cur, dict) and bool(cur.get("closed")) == want:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={"card": cur, "card_id": cid, "skipped": True, "reason": "already_in_state"},
                    )
            st, c = card_tools.set_card_closed(str(cid), want)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": cid})

        if ask == "set_card_due_complete":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            due_complete = ins.get("dueComplete")
            if due_complete is None:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["dueComplete"])
            want = bool(due_complete)
            st0, cur = card_tools.get_card_details(str(cid))
            if st0 >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st0}")
            if isinstance(cur, dict) and bool(cur.get("dueComplete")) == want:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"card": cur, "card_id": cid, "skipped": True, "reason": "already_in_state"},
                )
            st, c = card_tools.set_due_complete(str(cid), want)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": c.get("id", cid)})

        if ask == "set_card_due":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            if "due" not in ins:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["due"])
            due = ins.get("due")
            st, c = card_tools.set_due(str(cid), due if due not in ("", None) else None)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"card": c, "card_id": c.get("id", cid)})

        if ask == "add_card_member":
            cid = ins.get("card_id")
            mid = ins.get("member_id") or ins.get("idMember")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            if not mid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["member_id"])
            st0, cur = card_tools.get_card_details(str(cid))
            if st0 >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st0}")
            members = cur.get("idMembers") if isinstance(cur, dict) else None
            if isinstance(members, list) and str(mid) in [str(x) for x in members]:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"card": cur, "card_id": cid, "member_id": str(mid), "skipped": True, "reason": "already_in_state"},
                )
            st, _ = card_tools.add_member(str(cid), str(mid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            st2, after = card_tools.get_card_details(str(cid))
            card_out = after if st2 < 400 and isinstance(after, dict) else cur
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"card": card_out, "card_id": cid, "member_id": str(mid)},
            )

        if ask == "remove_card_member":
            cid = ins.get("card_id")
            mid = ins.get("member_id") or ins.get("idMember")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            if not mid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["member_id"])
            st, _ = card_tools.remove_card_member(str(cid), str(mid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"removed": True, "card_id": cid, "member_id": mid})

        if ask == "get_card_custom_field_items":
            cid = ins.get("card_id")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            params = {k: v for k, v in ins.items() if k in ("fields",)}
            st, items = card_tools.get_card_custom_field_items(str(cid), **params)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_field_items": items, "card_id": cid})

        if ask == "set_card_custom_field_item":
            cid = ins.get("card_id")
            cfid = ins.get("custom_field_id") or ins.get("idCustomField")
            if not cid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            if not cfid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["custom_field_id"])
            body = ins.get("body")
            if body is None and "value" in ins:
                body = {"value": ins["value"]}
            if not isinstance(body, dict):
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["body"])
            st, out = card_tools.set_card_custom_field_item(str(cid), str(cfid), body)
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"custom_field_item": out, "card_id": cid})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")

    def _extract_card_title(self, text: str) -> str:
        t = text.strip()
        if len(t) < 80 and "\n" not in t:
            return t
        return ""

    def _resolve_card(self, msg: A2AMessage, ins: dict[str, Any], mem: dict[str, Any]) -> A2AResponse:
        board_id = ins.get("board_id") or mem.get("board_id")
        hint = ins.get("card_hint") or ins.get("card_name") or ins.get("name") or ""
        uid = (msg.context or {}).get("user_text") or ""

        if not board_id:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["board_id"])

        if not hint:
            m = re.search(r"card\s+[\"']?([^\"'\n]+)[\"']?", uid, re.I)
            if m:
                hint = m.group(1).strip()
            # "move X to" pattern
            m2 = re.search(r"\bmove\s+(.+?)\s+(?:card\s+)?to\b", uid, re.I)
            if m2:
                hint = m2.group(1).replace("the", "").strip()

        lc = mem.get("last_cards") or []
        if isinstance(lc, list) and hint:
            narrowed = [
                x
                for x in lc
                if isinstance(x, dict) and hint and _card_name_matches_hint(str(hint), str(x.get("name", "")))
            ]
            if len(narrowed) == 1:
                x = narrowed[0]
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={
                        "card_id": x.get("id"),
                        "card_name": x.get("name"),
                        "list_name": x.get("list"),
                    },
                )
            if len(narrowed) > 1:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"matches": narrowed},
                    clarification="Which card? " + ", ".join(f"{m.get('name')} (list: {m.get('list')})" for m in narrowed[:6] if isinstance(m, dict)),
                )

        st, lists = board_tools.get_board_lists(str(board_id), cards="open")
        if st >= 400:
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")

        if not hint:
            # Continuation: user is editing "this card" after viewing one — use session focus.
            cid = mem.get("last_mentioned_card_id") or mem.get("last_card_id")
            cname = mem.get("last_card_name")
            if cid:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"card_id": cid, "card_name": cname, "list_name": None},
                )
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_hint"])

        matches = _match_cards(str(hint), [x for x in lists if isinstance(x, dict)])
        if len(matches) == 1:
            m = matches[0]
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"card_id": m.get("id"), "card_name": m.get("name"), "list_name": m.get("list")},
            )
        if len(matches) > 1:
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"matches": matches},
                clarification="Which card? " + ", ".join(f"{m.get('name')} (list: {m.get('list')})" for m in matches[:8]),
            )
        return A2AResponse(
            task_id=msg.task_id,
            frm=self.name,
            status="clarify_user",
            data={"hint": hint},
            clarification=f"I couldn't find a card matching {hint!r} on this board. Check the name?",
        )
