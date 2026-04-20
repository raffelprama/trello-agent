"""tool_observer — raw Trello JSON → compact parsed_response."""

from __future__ import annotations

from typing import Any

from app.state import ChatState


def _project_board(raw: dict[str, Any]) -> dict[str, Any]:
    return {"id": raw.get("id"), "name": raw.get("name")}


def _project_list(raw: dict[str, Any]) -> dict[str, Any]:
    return {"id": raw.get("id"), "name": raw.get("name")}


def _project_card(raw: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "due": raw.get("due"),
        "idList": raw.get("idList"),
    }
    if raw.get("_list_name"):
        out["list"] = raw["_list_name"]
    return out


def _project_label(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "color": raw.get("color"),
    }


def _project_checklist(raw: dict[str, Any]) -> dict[str, Any]:
    items_raw = raw.get("checkItems") or []
    items: list[dict[str, Any]] = []
    for it in items_raw:
        if isinstance(it, dict):
            items.append(
                {
                    "name": it.get("name"),
                    "state": it.get("state"),
                }
            )
    return {"id": raw.get("id"), "name": raw.get("name"), "items": items}


def _project_member(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "fullName": raw.get("fullName"),
        "username": raw.get("username"),
    }


def _resolve_list_name(id_list: str | None, lists: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not id_list or not lists:
        return None
    for lst in lists:
        if isinstance(lst, dict) and str(lst.get("id")) == str(id_list):
            return {"id": id_list, "name": lst.get("name")}
    return None


def _project_card_details(
    raw: dict[str, Any],
    lists: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    id_list = raw.get("idList")
    list_info = _resolve_list_name(str(id_list) if id_list else None, lists)
    out: dict[str, Any] = {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "desc": raw.get("desc") or "",
        "due": raw.get("due"),
        "dueComplete": raw.get("dueComplete"),
        "start": raw.get("start"),
        "shortUrl": raw.get("shortUrl"),
        "url": raw.get("url"),
    }
    if list_info:
        out["list"] = list_info
    elif id_list:
        out["idList"] = id_list
    labels = raw.get("labels")
    if isinstance(labels, list):
        out["labels"] = [_project_label(x) for x in labels if isinstance(x, dict)]
    else:
        out["labels"] = []
    checklists = raw.get("checklists")
    if isinstance(checklists, list):
        out["checklists"] = [_project_checklist(x) for x in checklists if isinstance(x, dict)]
    else:
        out["checklists"] = []
    members = raw.get("members")
    if isinstance(members, list):
        out["members"] = [_project_member(x) for x in members if isinstance(x, dict)]
    else:
        out["members"] = []
    badges = raw.get("badges")
    if isinstance(badges, dict):
        out["badges"] = {
            "comments": badges.get("comments"),
            "attachments": badges.get("attachments"),
            "checkItems": badges.get("checkItems"),
            "checkItemsChecked": badges.get("checkItemsChecked"),
        }
    return out


def tool_observer(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {"parsed_response": {}}

    intent = state.get("intent") or ""
    raw = state.get("raw_response")
    parsed: dict[str, Any] = {}
    ents: dict[str, Any] = state.get("entities") or {}

    if intent == "get_boards" and isinstance(raw, list):
        parsed["boards"] = [_project_board(x) for x in raw if isinstance(x, dict)]
    elif intent == "get_lists" and isinstance(raw, list):
        parsed["lists"] = [_project_list(x) for x in raw if isinstance(x, dict)]
    elif intent in ("get_cards", "get_board_cards") and isinstance(raw, list):
        parsed["cards"] = [_project_card(x) for x in raw if isinstance(x, dict)]
    elif intent == "get_card_details" and isinstance(raw, dict):
        lists = None
        if isinstance(ents.get("_lists"), list):
            lists = [x for x in ents["_lists"] if isinstance(x, dict)]
        parsed["card"] = _project_card_details(raw, lists)
    elif intent in ("create_card", "update_card", "move_card", "delete_card") and isinstance(
        raw, dict
    ):
        parsed["card"] = _project_card(raw)
        parsed["deleted"] = intent == "delete_card"
        parsed["raw"] = raw
    elif isinstance(raw, dict):
        parsed["data"] = raw
    else:
        parsed["data"] = raw

    if ents.get("board_id") or ents.get("resolved_board_name"):
        parsed["queried_board"] = {
            "id": ents.get("board_id"),
            "name": ents.get("resolved_board_name"),
        }

    return {"parsed_response": parsed}
