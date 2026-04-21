"""tool_router — intent + resolved entities → executor op payload (PRD v2)."""

from __future__ import annotations

from typing import Any

from app.config import DELETE_ITEM
from app.state import ChatState


def _err(msg: str) -> dict[str, Any]:
    return {"selected_tool": "error", "tool_input": {"message": msg}}


def tool_router(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {"selected_tool": "none", "tool_input": {}}

    intent = state.get("intent") or ""
    entities = state.get("entities") or {}
    payload: dict[str, Any] = {"op": intent}

    bid = entities.get("board_id")
    cid = entities.get("card_id")
    lid = entities.get("list_id")
    tlid = entities.get("target_list_id")

    if intent == "get_member_me":
        return {"selected_tool": "get_member_me", "tool_input": payload}

    if intent == "get_boards":
        return {"selected_tool": "get_boards", "tool_input": payload}

    if intent == "get_board":
        if not bid:
            return _err("Missing board_id for get_board")
        payload["board_id"] = bid
        return {"selected_tool": "get_board", "tool_input": payload}

    if intent == "create_board":
        name = entities.get("new_board_name") or entities.get("board_name")
        if not name:
            return _err("create_board requires new_board_name or board_name")
        payload["name"] = str(name)
        if entities.get("description") is not None:
            payload["desc"] = str(entities["description"])
        return {"selected_tool": "create_board", "tool_input": payload}

    if intent == "update_board":
        if not bid:
            return _err("Missing board_id for update_board")
        payload["board_id"] = bid
        if entities.get("new_board_name"):
            payload["name"] = str(entities["new_board_name"])
        if entities.get("description") is not None:
            payload["desc"] = str(entities["description"])
        return {"selected_tool": "update_board", "tool_input": payload}

    if intent == "get_lists":
        if not bid:
            return _err("Missing board_id for get_lists")
        payload["board_id"] = bid
        return {"selected_tool": "get_lists", "tool_input": payload}

    if intent == "create_list":
        if not bid:
            return _err("Missing board_id for create_list")
        ln = entities.get("list_name")
        if not ln:
            return _err("create_list requires list_name")
        payload["board_id"] = bid
        payload["name"] = str(ln)
        return {"selected_tool": "create_list", "tool_input": payload}

    if intent == "update_list":
        if not lid:
            return _err("Missing list_id for update_list")
        payload["list_id"] = lid
        new_name = entities.get("new_list_name") or entities.get("list_name")
        if new_name:
            payload["name"] = str(new_name)
        return {"selected_tool": "update_list", "tool_input": payload}

    if intent == "archive_list":
        if not lid:
            return _err("Missing list_id for archive_list")
        payload["list_id"] = lid
        payload["closed"] = True
        return {"selected_tool": "archive_list", "tool_input": payload}

    if intent == "get_board_cards":
        if not bid:
            return _err("Missing board_id for get_board_cards")
        payload["board_id"] = bid
        return {"selected_tool": "get_board_cards", "tool_input": payload}

    if intent == "get_cards":
        if not lid:
            return _err("Missing list_id for get_cards")
        payload["list_id"] = lid
        return {"selected_tool": "get_cards", "tool_input": payload}

    if intent == "get_card_details":
        if not cid:
            return _err("get_card_details requires card_id")
        payload["card_id"] = cid
        return {"selected_tool": "get_card_details", "tool_input": payload}

    if intent == "create_card":
        if not lid or not entities.get("card_name"):
            return _err("create_card requires list_id and card_name")
        payload["id_list"] = lid
        payload["name"] = str(entities["card_name"])
        if entities.get("description"):
            payload["desc"] = str(entities["description"])
        if entities.get("due"):
            payload["due"] = str(entities["due"])
        return {"selected_tool": "create_card", "tool_input": payload}

    if intent == "update_card":
        if not cid:
            return _err("Missing card_id for update_card")
        payload["card_id"] = cid
        if entities.get("description") is not None:
            payload["desc"] = str(entities["description"])
        if entities.get("due"):
            payload["due"] = str(entities["due"])
        if entities.get("new_card_name"):
            payload["name"] = str(entities["new_card_name"])
        return {"selected_tool": "update_card", "tool_input": payload}

    if intent == "move_card":
        if not cid or not tlid:
            return _err("move_card requires card_id and target_list_id")
        payload["card_id"] = cid
        payload["id_list"] = tlid
        if entities.get("_already_in_target_list"):
            payload["_noop"] = True
        return {"selected_tool": "move_card", "tool_input": payload}

    if intent == "delete_card":
        if not DELETE_ITEM:
            return _err("delete_card is disabled (DELETE_ITEM=false in .env)")
        if not cid:
            return _err("Missing card_id for delete_card")
        payload["card_id"] = cid
        return {"selected_tool": "delete_card", "tool_input": payload}

    if intent == "get_card_checklists":
        if not cid:
            return _err("Missing card_id")
        payload["card_id"] = cid
        return {"selected_tool": "get_card_checklists", "tool_input": payload}

    if intent == "create_checklist":
        if not cid or not entities.get("checklist_name"):
            return _err("create_checklist requires card_id and checklist_name")
        payload["card_id"] = cid
        payload["name"] = str(entities["checklist_name"])
        return {"selected_tool": "create_checklist", "tool_input": payload}

    if intent == "delete_checklist":
        chid = entities.get("checklist_id")
        if not chid:
            return _err("delete_checklist requires checklist_id (resolve checklist name first)")
        payload["checklist_id"] = chid
        return {"selected_tool": "delete_checklist", "tool_input": payload}

    if intent == "get_checkitems":
        chid = entities.get("checklist_id")
        if not chid:
            return _err("get_checkitems requires checklist_id")
        payload["checklist_id"] = chid
        return {"selected_tool": "get_checkitems", "tool_input": payload}

    if intent == "create_checkitem":
        chid = entities.get("checklist_id")
        if not chid or not entities.get("check_item_name"):
            return _err("create_checkitem requires checklist_id and check_item_name")
        payload["checklist_id"] = chid
        payload["name"] = str(entities["check_item_name"])
        return {"selected_tool": "create_checkitem", "tool_input": payload}

    if intent == "check_item":
        ciid = entities.get("check_item_id")
        if not cid or not ciid:
            return _err("check_item requires card_id and check_item_id")
        payload["card_id"] = cid
        payload["check_item_id"] = ciid
        payload["state"] = "complete"
        return {"selected_tool": "check_item", "tool_input": payload}

    if intent == "uncheck_item":
        ciid = entities.get("check_item_id")
        if not cid or not ciid:
            return _err("uncheck_item requires card_id and check_item_id")
        payload["card_id"] = cid
        payload["check_item_id"] = ciid
        payload["state"] = "incomplete"
        return {"selected_tool": "uncheck_item", "tool_input": payload}

    if intent == "delete_checkitem":
        chid = entities.get("checklist_id")
        ciid = entities.get("check_item_id")
        if not chid or not ciid:
            return _err("delete_checkitem requires checklist_id and check_item_id")
        payload["checklist_id"] = chid
        payload["check_item_id"] = ciid
        return {"selected_tool": "delete_checkitem", "tool_input": payload}

    if intent == "get_comments":
        if not cid:
            return _err("Missing card_id for get_comments")
        payload["card_id"] = cid
        return {"selected_tool": "get_comments", "tool_input": payload}

    if intent == "create_comment":
        if not cid or not entities.get("comment_text"):
            return _err("create_comment requires card_id and comment_text")
        payload["card_id"] = cid
        payload["text"] = str(entities["comment_text"])
        return {"selected_tool": "create_comment", "tool_input": payload}

    if intent == "update_comment":
        aid = entities.get("action_id")
        if not aid or entities.get("comment_text") is None:
            return _err("update_comment requires action_id and comment_text")
        payload["action_id"] = str(aid)
        payload["text"] = str(entities["comment_text"])
        return {"selected_tool": "update_comment", "tool_input": payload}

    if intent == "delete_comment":
        aid = entities.get("action_id")
        if not aid:
            return _err("delete_comment requires action_id")
        payload["action_id"] = str(aid)
        return {"selected_tool": "delete_comment", "tool_input": payload}

    if intent == "get_board_labels":
        if not bid:
            return _err("Missing board_id for get_board_labels")
        payload["board_id"] = bid
        return {"selected_tool": "get_board_labels", "tool_input": payload}

    if intent == "create_label":
        if not bid or not entities.get("label_name"):
            return _err("create_label requires board_id and label_name")
        payload["board_id"] = bid
        payload["name"] = str(entities["label_name"])
        if entities.get("color"):
            payload["color"] = str(entities["color"])
        return {"selected_tool": "create_label", "tool_input": payload}

    if intent == "add_card_label":
        if not cid or not entities.get("label_id"):
            return _err("add_card_label requires card_id and label_id")
        payload["card_id"] = cid
        payload["label_id"] = str(entities["label_id"])
        return {"selected_tool": "add_card_label", "tool_input": payload}

    if intent == "remove_card_label":
        if not cid or not entities.get("label_id"):
            return _err("remove_card_label requires card_id and label_id")
        payload["card_id"] = cid
        payload["label_id"] = str(entities["label_id"])
        return {"selected_tool": "remove_card_label", "tool_input": payload}

    if intent == "get_board_members":
        if not bid:
            return _err("Missing board_id for get_board_members")
        payload["board_id"] = bid
        return {"selected_tool": "get_board_members", "tool_input": payload}

    if intent == "get_board_actions":
        if not bid:
            return _err("Missing board_id for get_board_actions")
        payload["board_id"] = bid
        if entities.get("filter"):
            payload["filter"] = str(entities["filter"])
        return {"selected_tool": "get_board_actions", "tool_input": payload}

    return _err(f"Unknown intent {intent}")
