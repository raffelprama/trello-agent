"""ChecklistAgent — card checklists, items, state via PUT /cards/{id}/checkItem/{id}."""

from __future__ import annotations

from typing import Any

from app.agents.base import A2AMessage, A2AResponse, BaseAgent
from app.tools import card as card_tools
from app.tools import checklist as cl_tools
from app.utils.resolution import close_name_matches, match_dicts_by_name


def _check_items_for_checklist(ch: dict[str, Any]) -> list[dict[str, Any]]:
    """Use embedded checkItems from card checklists payload when present; else GET checkItems."""
    raw = ch.get("checkItems")
    if isinstance(raw, list) and raw:
        return [x for x in raw if isinstance(x, dict) and x.get("id")]
    cid = ch.get("id")
    if not cid:
        return []
    st, items = cl_tools.get_checkitems(str(cid))
    if st >= 400 or not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("id")]


class ChecklistAgent(BaseAgent):
    name = "checklist"

    def handle(self, msg: A2AMessage) -> A2AResponse:
        ask = msg.ask
        ins = dict((msg.context or {}).get("_resolved_inputs") or {})
        card_id = ins.get("card_id")

        if ask == "list_checklists":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, rows = card_tools.get_card_checklists(str(card_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"checklists": rows, "card_id": card_id})

        if ask == "create_checklist":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            name = ins.get("name") or ins.get("checklist_name")
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, ch = card_tools.post_card_checklist(str(card_id), str(name))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="ok",
                data={"checklist": ch, "checklist_id": ch.get("id") if isinstance(ch, dict) else None},
            )

        if ask == "resolve_checklist":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            st, rows = card_tools.get_card_checklists(str(card_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            dict_rows = [ch for ch in (rows or []) if isinstance(ch, dict) and ch.get("id")]
            name_hint = str(ins.get("checklist_name") or ins.get("name") or "").strip()
            item_name = str(ins.get("item_name") or ins.get("check_item_name") or "").strip()

            if not name_hint:
                inferred: list[dict[str, Any]] = []
                if item_name:
                    for ch in dict_rows:
                        dict_items = _check_items_for_checklist(ch)
                        if match_dicts_by_name(item_name, dict_items):
                            inferred.append(ch)
                if len(inferred) == 1:
                    ch0 = inferred[0]
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={
                            "checklist_id": ch0.get("id"),
                            "checklist": ch0,
                            "created": False,
                            "inferred_from": "item_name",
                        },
                    )
                if len(inferred) > 1:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="clarify_user",
                        data={"candidates": inferred[:15]},
                        clarification=(
                            "That checklist item name appears on more than one checklist — which checklist? "
                            + ", ".join(str(c.get("name") or "") for c in inferred if isinstance(c, dict))
                        ),
                    )
                if len(dict_rows) == 1:
                    ch0 = dict_rows[0]
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={"checklist_id": ch0.get("id"), "checklist": ch0, "created": False, "inferred_from": "single_checklist"},
                    )
                if not dict_rows:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="clarify_user",
                        data={"candidates": []},
                        clarification="This card has no checklists yet. Ask to create a checklist first, or name the checklist to use.",
                    )
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"candidates": dict_rows[:30]},
                    clarification=(
                        "Which checklist should this apply to? Options: "
                        + ", ".join(str(c.get("name") or "") for c in dict_rows if isinstance(c, dict))
                        + ". Tip: repeat the item text in resolve_checklist.item_name (same as the item you add or check) to auto-pick the checklist."
                    ),
                )

            hit = match_dicts_by_name(name_hint, dict_rows)
            if hit:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"checklist_id": hit.get("id"), "checklist": hit, "created": False},
                )
            nh = " ".join(name_hint.strip().lower().split())
            if nh:
                multi_sub: list[dict[str, Any]] = []
                for ch in dict_rows:
                    cn = " ".join(str(ch.get("name", "")).strip().lower().split())
                    if cn and nh in cn:
                        multi_sub.append(ch)
                if len(multi_sub) > 1:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="clarify_user",
                        data={"candidates": multi_sub[:15]},
                        clarification=(
                            f"Several checklists match {name_hint!r} — which one? "
                            + ", ".join(str(c.get("name") or "") for c in multi_sub if isinstance(c, dict))
                        ),
                    )
            close = close_name_matches(
                name_hint,
                dict_rows,
                get_name=lambda d: str(d.get("name", "")),
                max_levenshtein=2,
                max_results=8,
            )
            if close:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"candidates": close},
                    clarification=(
                        f"No unique checklist match for {name_hint!r} — did you mean one of: "
                        + ", ".join(str(c.get("name") or "") for c in close if isinstance(c, dict))
                        + "?"
                    ),
                )
            create_if_missing = ins.get("create_if_missing")
            if create_if_missing is None:
                create_if_missing = True
            if create_if_missing:
                st2, ch = card_tools.post_card_checklist(str(card_id), name_hint)
                if st2 >= 400:
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st2} creating checklist")
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={"checklist_id": ch.get("id"), "checklist": ch, "created": True},
                )
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"candidates": dict_rows[:30]},
                clarification=f"I couldn't find checklist {name_hint!r} on this card. Which checklist?",
            )

        if ask == "resolve_check_item":
            checklist_id = ins.get("checklist_id")
            name_hint = str(ins.get("item_name") or ins.get("name") or "").strip()
            checklist_name_hint = str(ins.get("checklist_name") or "").strip()
            if not name_hint:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["item_name"])

            if not checklist_id and checklist_name_hint and card_id:
                st_ch, ch_rows = card_tools.get_card_checklists(str(card_id))
                if st_ch >= 400:
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_ch}")
                dict_rows = [ch for ch in (ch_rows or []) if isinstance(ch, dict) and ch.get("id")]
                ch_hit = match_dicts_by_name(checklist_name_hint, dict_rows)
                if not ch_hit:
                    close_ch = close_name_matches(
                        checklist_name_hint,
                        dict_rows,
                        get_name=lambda d: str(d.get("name", "")),
                        max_levenshtein=2,
                        max_results=8,
                    )
                    if close_ch:
                        return A2AResponse(
                            task_id=msg.task_id,
                            frm=self.name,
                            status="clarify_user",
                            data={"candidates": close_ch},
                            clarification=(
                                f"No unique checklist match for {checklist_name_hint!r} — did you mean: "
                                + ", ".join(str(c.get("name") or "") for c in close_ch if isinstance(c, dict))
                                + "?"
                            ),
                        )
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="clarify_user",
                        data={"candidates": dict_rows[:30]},
                        clarification=f"I couldn't find checklist {checklist_name_hint!r}. Which checklist?",
                    )
                checklist_id = ch_hit.get("id")

            if not checklist_id:
                if not card_id:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="need_info",
                        data={},
                        missing=["card_id"],
                    )
                st_ch, ch_rows = card_tools.get_card_checklists(str(card_id))
                if st_ch >= 400:
                    return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st_ch}")
                flat: list[dict[str, Any]] = []
                for ch in ch_rows or []:
                    if not isinstance(ch, dict):
                        continue
                    cid_ch = ch.get("id")
                    if not cid_ch:
                        continue
                    st_it, items = cl_tools.get_checkitems(str(cid_ch))
                    if st_it >= 400 or not isinstance(items, list):
                        continue
                    for it in items:
                        if isinstance(it, dict) and it.get("id"):
                            flat.append({"checklist_id": str(cid_ch), "check_item_id": it.get("id"), "name": str(it.get("name") or ""), "item": it})
                m = match_dicts_by_name(name_hint, flat)
                if m:
                    it = m.get("item")
                    _cid = m.get("check_item_id")
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="ok",
                        data={
                            "check_item_id": _cid,
                            "checkitem_id": _cid,
                            "checklist_id": m.get("checklist_id"),
                            "item": it if isinstance(it, dict) else m,
                        },
                    )
                close_items = close_name_matches(
                    name_hint,
                    flat,
                    get_name=lambda row: str(row.get("name", "")),
                    max_levenshtein=2,
                    max_results=12,
                )
                if close_items:
                    return A2AResponse(
                        task_id=msg.task_id,
                        frm=self.name,
                        status="clarify_user",
                        data={"candidates": close_items},
                        clarification=(
                            "Which check item? Close matches: "
                            + ", ".join(
                                f"{c.get('name')} (checklist id {c.get('checklist_id')})"
                                for c in close_items
                                if isinstance(c, dict)
                            )
                        ),
                    )
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"candidates": flat[:50]},
                    clarification="Which check item? No unique match across this card's checklists.",
                )

            st, items = cl_tools.get_checkitems(str(checklist_id))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            dict_items = [it for it in items if isinstance(it, dict)]
            hit = match_dicts_by_name(name_hint, dict_items)
            if hit:
                _iid = hit.get("id")
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="ok",
                    data={
                        "check_item_id": _iid,
                        "checkitem_id": _iid,
                        "checklist_id": str(checklist_id),
                        "item": hit,
                    },
                )
            close_one = close_name_matches(
                name_hint,
                dict_items,
                get_name=lambda it: str(it.get("name", "")),
                max_levenshtein=2,
                max_results=12,
            )
            if close_one:
                return A2AResponse(
                    task_id=msg.task_id,
                    frm=self.name,
                    status="clarify_user",
                    data={"candidates": close_one},
                    clarification="Which check item? Close matches: "
                    + ", ".join(str(c.get("name") or "") for c in close_one if isinstance(c, dict)),
                )
            return A2AResponse(
                task_id=msg.task_id,
                frm=self.name,
                status="clarify_user",
                data={"items": items},
                clarification="Which check item?",
            )

        if ask == "set_checkitem_state":
            if not card_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["card_id"])
            ciid = ins.get("check_item_id") or ins.get("checkitem_id")
            state = ins.get("state") or "complete"
            if not ciid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["check_item_id"])
            want = "complete" if str(state).lower() in ("complete", "true", "1", "yes") else "incomplete"
            if not ins.get("skip_idempotency_check"):
                st_ch, ch_rows = card_tools.get_card_checklists(str(card_id))
                if st_ch < 400 and isinstance(ch_rows, list):
                    found_other_state = False
                    for ch in ch_rows:
                        if not isinstance(ch, dict):
                            continue
                        st_it, items = cl_tools.get_checkitems(str(ch.get("id", "")))
                        if st_it >= 400 or not isinstance(items, list):
                            continue
                        for it in items:
                            if isinstance(it, dict) and str(it.get("id")) == str(ciid):
                                if str(it.get("state", "")).lower() == want:
                                    return A2AResponse(
                                        task_id=msg.task_id,
                                        frm=self.name,
                                        status="ok",
                                        data={"result": it, "skipped": True, "reason": "already_in_state"},
                                    )
                                found_other_state = True
                                break
                        if found_other_state:
                            break
            st, data = cl_tools.set_checkitem_state(str(card_id), str(ciid), str(state))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"result": data})

        if ask == "create_checkitem":
            checklist_id = ins.get("checklist_id")
            name = ins.get("name") or ins.get("item_name")
            if not checklist_id:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_id"])
            if not name:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["name"])
            st, data = cl_tools.create_checkitem(str(checklist_id), str(name))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"checkItem": data})

        if ask == "delete_checkitem":
            checklist_id = ins.get("checklist_id")
            ciid = ins.get("check_item_id") or ins.get("checkitem_id")
            if not checklist_id or not ciid:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="need_info", data={}, missing=["checklist_id", "check_item_id"])
            st, data = cl_tools.delete_checkitem(str(checklist_id), str(ciid))
            if st >= 400:
                return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"HTTP {st}")
            return A2AResponse(task_id=msg.task_id, frm=self.name, status="ok", data={"deleted": True})

        return A2AResponse(task_id=msg.task_id, frm=self.name, status="error", data={}, error=f"Unknown ask={ask!r}")
