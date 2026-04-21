"""tool_observer — raw Trello JSON → compact parsed_response (PRD v2)."""

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
                    "id": it.get("id"),
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


def _project_action_short(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "type": raw.get("type"),
        "date": raw.get("date"),
        "text": (raw.get("data") or {}).get("text") if isinstance(raw.get("data"), dict) else None,
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

    if intent == "get_member_me" and isinstance(raw, dict):
        parsed["member"] = {
            "id": raw.get("id"),
            "fullName": raw.get("fullName"),
            "username": raw.get("username"),
        }
    elif intent == "get_boards" and isinstance(raw, list):
        parsed["boards"] = [_project_board(x) for x in raw if isinstance(x, dict)]
    elif intent == "get_board" and isinstance(raw, dict):
        parsed["board"] = _project_board(raw)
    elif intent in ("create_board", "update_board") and isinstance(raw, dict):
        parsed["board"] = _project_board(raw)
    elif intent == "get_lists" and isinstance(raw, list):
        parsed["lists"] = [_project_list(x) for x in raw if isinstance(x, dict)]
    elif intent in ("create_list", "update_list", "archive_list") and isinstance(raw, dict):
        parsed["list"] = _project_list(raw)
    elif intent in ("get_cards", "get_board_cards") and isinstance(raw, list):
        parsed["cards"] = [_project_card(x) for x in raw if isinstance(x, dict)]
    elif intent == "get_card_details" and isinstance(raw, dict):
        lists = None
        if isinstance(ents.get("_lists"), list):
            lists = [x for x in ents["_lists"] if isinstance(x, dict)]
        parsed["card"] = _project_card_details(raw, lists)
    elif intent in ("create_card", "update_card", "move_card", "delete_card") and isinstance(raw, dict):
        parsed["card"] = _project_card(raw)
        parsed["deleted"] = intent == "delete_card"
        parsed["raw"] = raw
    elif intent == "get_card_checklists" and isinstance(raw, list):
        parsed["checklists"] = [_project_checklist(x) for x in raw if isinstance(x, dict)]
    elif intent == "create_checklist" and isinstance(raw, dict):
        parsed["checklist"] = {"id": raw.get("id"), "name": raw.get("name")}
    elif intent == "delete_checklist":
        parsed["deleted"] = True
    elif intent == "get_checkitems" and isinstance(raw, list):
        parsed["checkItems"] = [
            {"id": x.get("id"), "name": x.get("name"), "state": x.get("state")}
            for x in raw
            if isinstance(x, dict)
        ]
    elif intent == "create_checkitem" and isinstance(raw, dict):
        parsed["checkItem"] = {"id": raw.get("id"), "name": raw.get("name"), "state": raw.get("state")}
    elif intent in ("check_item", "uncheck_item") and isinstance(raw, dict):
        parsed["checkItem"] = {"id": raw.get("id"), "name": raw.get("name"), "state": raw.get("state")}
    elif intent == "delete_checkitem":
        parsed["deleted"] = True
    elif intent == "get_comments" and isinstance(raw, list):
        parsed["comments"] = [_project_action_short(x) for x in raw if isinstance(x, dict)]
    elif intent == "create_comment" and isinstance(raw, dict):
        parsed["comment"] = _project_action_short(raw)
    elif intent in ("update_comment", "delete_comment") and isinstance(raw, dict):
        parsed["action"] = _project_action_short(raw)
    elif intent == "get_board_labels" and isinstance(raw, list):
        parsed["labels"] = [_project_label(x) for x in raw if isinstance(x, dict)]
    elif intent == "create_label" and isinstance(raw, dict):
        parsed["label"] = _project_label(raw)
    elif intent in ("add_card_label", "remove_card_label"):
        parsed["ok"] = True
    elif intent == "get_board_members" and isinstance(raw, list):
        parsed["members"] = [_project_member(x) for x in raw if isinstance(x, dict)]
    elif intent == "get_board_actions" and isinstance(raw, list):
        parsed["actions"] = [_project_action_short(x) for x in raw if isinstance(x, dict)]
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
