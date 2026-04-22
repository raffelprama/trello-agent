"""Working memory across CLI turns — built from parsed_response + plan results."""

from __future__ import annotations

from typing import Any


def empty_memory() -> dict[str, Any]:
    return {
        "board_id": None,
        "board_name": None,
        "list_map": [],  # [{id, name}]
        "last_cards": [],  # [{name, list, id?}]
        "last_card_id": None,
        "last_card_name": None,
        "pending_clarify": None,
        "pending_plan": None,  # {plan: dict, ...} — A2A resume
    }


def merge_memory(prev: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge; list_map/last_cards replaced when update provides them."""
    base = dict(empty_memory())
    if prev:
        base.update({k: v for k, v in prev.items() if v is not None})
    for k, v in update.items():
        if v is not None:
            base[k] = v
    return base


def memory_summary_for_planner(mem: dict[str, Any] | None) -> str:
    """Compact string for LLM prompt."""
    if not mem:
        return "(no prior session memory)"
    lines: list[str] = []
    if mem.get("board_id"):
        lines.append(f"board_id={mem.get('board_id')} name={mem.get('board_name')!r}")
    lm = mem.get("list_map")
    if isinstance(lm, list) and lm:
        names = [str(x.get("name", "")) for x in lm if isinstance(x, dict)][:20]
        lines.append(f"lists on board: {', '.join(names)}")
    lc = mem.get("last_cards")
    if isinstance(lc, list) and lc:
        for i, c in enumerate(lc[:30]):
            if isinstance(c, dict):
                lines.append(
                    f"  card[{i}]: name={c.get('name')!r} list={c.get('list')!r} id={c.get('id')!r}",
                )
    if mem.get("last_card_id"):
        lines.append(f"last_focused_card_id={mem.get('last_card_id')} name={mem.get('last_card_name')!r}")
    pp = mem.get("pending_plan")
    if isinstance(pp, dict) and pp.get("plan"):
        lines.append("pending_plan: present (continuation expected for blocked step)")
    pc = mem.get("pending_clarify")
    if isinstance(pc, dict) and pc.get("kind"):
        amb = pc.get("ambiguous") or {}
        if amb.get("kind") == "multiple_cards":
            names = ", ".join(
                f"{m.get('name')} (list: {m.get('list')})"
                for m in (amb.get("matches") or [])[:5]
                if isinstance(m, dict)
            )
            lines.append(f"pending_clarification: asked which card from [{names}]")
        elif amb.get("kind") == "card_name_missing":
            lines.append("pending_clarification: asked user to provide the card name")
        else:
            lines.append(
                f"pending_clarification: {pc.get('kind')!r} — {str(pc.get('question', ''))[:120]}"
            )
    return "\n".join(lines) if lines else "(empty memory)"


def extract_from_parsed_and_entities(
    parsed: dict[str, Any],
    entities: dict[str, Any],
    intent: str,
) -> dict[str, Any]:
    """Return fields to merge into session memory after a successful turn (legacy)."""
    out: dict[str, Any] = {}
    if entities.get("board_id"):
        out["board_id"] = entities.get("board_id")
    if entities.get("resolved_board_name"):
        out["board_name"] = entities.get("resolved_board_name")
    elif parsed.get("queried_board", {}).get("name"):
        out["board_name"] = parsed["queried_board"]["name"]

    lists_raw = entities.get("_lists")
    if isinstance(lists_raw, list):
        out["list_map"] = [
            {"id": x.get("id"), "name": x.get("name")}
            for x in lists_raw
            if isinstance(x, dict) and x.get("id")
        ]

    if intent in ("create_board", "get_board") and isinstance(parsed.get("board"), dict):
        b = parsed["board"]
        if b.get("id"):
            out["board_id"] = b.get("id")
        if b.get("name"):
            out["board_name"] = b.get("name")

    if intent in ("get_board_cards", "get_cards") and isinstance(parsed.get("cards"), list):
        cards_out: list[dict[str, Any]] = []
        for c in parsed["cards"]:
            if not isinstance(c, dict):
                continue
            cards_out.append(
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "list": c.get("list"),
                }
            )
        out["last_cards"] = cards_out
        if cards_out:
            out["last_card_id"] = cards_out[-1].get("id")
            out["last_card_name"] = cards_out[-1].get("name")

    if intent == "get_card_details" and isinstance(parsed.get("card"), dict):
        cd = parsed["card"]
        cid = cd.get("id")
        if cid:
            out["last_card_id"] = cid
            out["last_card_name"] = cd.get("name")
        lst = cd.get("list")
        lname = None
        if isinstance(lst, dict):
            lname = lst.get("name")
        elif isinstance(lst, str):
            lname = lst
        if cid and cd.get("name"):
            row = {"id": cid, "name": cd.get("name"), "list": lname}
            prev_lc = out.get("last_cards")
            if not isinstance(prev_lc, list):
                prev_lc = []
            ids = {str(x.get("id")) for x in prev_lc if isinstance(x, dict) and x.get("id")}
            if str(cid) not in ids:
                prev_lc = prev_lc + [row]
            out["last_cards"] = prev_lc

    return out


def extract_from_plan_parsed(parsed: dict[str, Any], entities: dict[str, Any]) -> dict[str, Any]:
    """Memory update from A2A aggregated parsed_response."""
    out: dict[str, Any] = {}
    if entities.get("board_id"):
        out["board_id"] = entities.get("board_id")
    if entities.get("resolved_board_name"):
        out["board_name"] = entities.get("resolved_board_name")
    qb = parsed.get("queried_board")
    if isinstance(qb, dict) and qb.get("id"):
        out["board_id"] = qb.get("id")
    if isinstance(parsed.get("lists"), list) and parsed["lists"]:
        out["list_map"] = [
            {"id": x.get("id"), "name": x.get("name")}
            for x in parsed["lists"]
            if isinstance(x, dict) and x.get("id")
        ]
    if isinstance(parsed.get("cards"), list):
        cards_out: list[dict[str, Any]] = []
        for c in parsed["cards"]:
            if not isinstance(c, dict):
                continue
            cards_out.append(
                {
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "list": c.get("list"),
                }
            )
        if cards_out:
            out["last_cards"] = cards_out
            out["last_card_id"] = cards_out[-1].get("id")
            out["last_card_name"] = cards_out[-1].get("name")
    if isinstance(parsed.get("card"), dict):
        cd = parsed["card"]
        if cd.get("id"):
            out["last_card_id"] = cd.get("id")
            out["last_card_name"] = cd.get("name")
    return out


def set_pending_clarify(mem: dict[str, Any], pending: dict[str, Any] | None) -> dict[str, Any]:
    m = dict(mem or empty_memory())
    m["pending_clarify"] = pending
    return m


def clear_pending_clarify(mem: dict[str, Any]) -> dict[str, Any]:
    m = dict(mem or empty_memory())
    m["pending_clarify"] = None
    return m


def finalize_turn_memory(prev: dict[str, Any] | None, out: dict[str, Any]) -> dict[str, Any]:
    """Update working memory after a graph turn (CLI + API)."""
    base = dict(prev or empty_memory())
    parsed = out.get("parsed_response") or {}
    ent = out.get("entities") or {}
    intent = str(out.get("intent") or "")
    clarification = isinstance(parsed, dict) and parsed.get("clarification")
    ev = out.get("evaluation_result") or {}
    payload = out.get("pending_plan_payload")

    if clarification or out.get("needs_clarification") or ev.get("reason") == "clarification":
        amb = out.get("ambiguous_entities") or {}
        m = set_pending_clarify(
            base,
            {
                "kind": "clarify",
                "question": out.get("clarification_question") or out.get("answer"),
                "ambiguous": amb,
            },
        )
        if isinstance(payload, dict) and payload.get("plan"):
            m["pending_plan"] = payload
        elif isinstance(out.get("plan"), dict) and out.get("plan", {}).get("plan_id"):
            m["pending_plan"] = {"plan": out["plan"]}
        return m

    if ev.get("status") == "success" and not out.get("error_message"):
        upd = extract_from_plan_parsed(parsed if isinstance(parsed, dict) else {}, ent if isinstance(ent, dict) else {})
        if not upd.get("board_id") and not upd.get("last_cards"):
            upd = extract_from_parsed_and_entities(
                parsed if isinstance(parsed, dict) else {},
                ent if isinstance(ent, dict) else {},
                intent,
            )
        m = clear_pending_clarify(merge_memory(base, upd))
        m["pending_plan"] = None
        return m

    return base
