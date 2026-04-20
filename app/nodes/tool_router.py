"""tool_router — intent + resolved entities → executor op payload."""

from __future__ import annotations

from typing import Any

from app.config import DELETE_ITEM
from app.state import ChatState


def tool_router(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {"selected_tool": "none", "tool_input": {}}

    intent = state.get("intent") or ""
    entities = state.get("entities") or {}

    payload: dict[str, Any] = {"op": intent}

    if intent == "get_boards":
        return {"selected_tool": "get_boards", "tool_input": payload}

    if intent == "get_lists":
        bid = entities.get("board_id")
        if not bid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "Missing board_id for get_lists"},
            }
        payload["board_id"] = bid
        return {"selected_tool": "get_lists", "tool_input": payload}

    if intent == "get_board_cards":
        bid = entities.get("board_id")
        if not bid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "Missing board_id for get_board_cards"},
            }
        payload["board_id"] = bid
        return {"selected_tool": "get_board_cards", "tool_input": payload}

    if intent == "get_card_details":
        cid = entities.get("card_id")
        if not cid:
            return {
                "selected_tool": "error",
                "tool_input": {
                    "message": "get_card_details requires card_id (resolve card name on the board first)",
                },
            }
        payload["card_id"] = cid
        return {"selected_tool": "get_card_details", "tool_input": payload}

    if intent == "get_cards":
        lid = entities.get("list_id")
        if not lid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "Missing list_id for get_cards"},
            }
        payload["list_id"] = lid
        return {"selected_tool": "get_cards", "tool_input": payload}

    if intent == "create_card":
        lid = entities.get("list_id")
        name = entities.get("card_name")
        if not lid or not name:
            return {
                "selected_tool": "error",
                "tool_input": {
                    "message": "create_card requires list_id and card_name",
                },
            }
        payload["id_list"] = lid
        payload["name"] = str(name)
        if entities.get("description"):
            payload["desc"] = str(entities["description"])
        if entities.get("due"):
            payload["due"] = str(entities["due"])
        return {"selected_tool": "create_card", "tool_input": payload}

    if intent == "update_card":
        cid = entities.get("card_id")
        if not cid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "Missing card_id for update_card"},
            }
        payload["card_id"] = cid
        if entities.get("description") is not None:
            payload["desc"] = str(entities["description"])
        if entities.get("due"):
            payload["due"] = str(entities["due"])
        if entities.get("new_card_name"):
            payload["name"] = str(entities["new_card_name"])
        return {"selected_tool": "update_card", "tool_input": payload}

    if intent == "move_card":
        cid = entities.get("card_id")
        tlid = entities.get("target_list_id")
        if not cid or not tlid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "move_card requires card_id and target_list_id"},
            }
        payload["card_id"] = cid
        payload["id_list"] = tlid
        return {"selected_tool": "move_card", "tool_input": payload}

    if intent == "delete_card":
        if not DELETE_ITEM:
            return {
                "selected_tool": "error",
                "tool_input": {
                    "message": "delete_card is disabled (DELETE_ITEM=false in .env)",
                },
            }
        cid = entities.get("card_id")
        if not cid:
            return {
                "selected_tool": "error",
                "tool_input": {"message": "Missing card_id for delete_card"},
            }
        payload["card_id"] = cid
        return {"selected_tool": "delete_card", "tool_input": payload}

    return {"selected_tool": "error", "tool_input": {"message": f"Unknown intent {intent}"}}
