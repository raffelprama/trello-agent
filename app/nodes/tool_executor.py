"""tool_executor — dispatch to app.tools.* and TrelloClient."""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any

from app.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.state import ChatState
from app.tools import action as action_tools
from app.tools import board as board_tools
from app.tools import card as card_tools
from app.tools import checklist as checklist_tools
from app.tools import list_ops as list_tools
from app.tools import member as member_tools
from app.trello_client import get_client

logger = logging.getLogger(__name__)


def tool_executor(state: ChatState) -> dict[str, Any]:
    if state.get("skip_tools"):
        return {}

    tool_input = dict(state.get("tool_input") or {})
    selected = state.get("selected_tool") or "error"

    if selected == "error":
        msg = tool_input.get("message", "Unknown routing error")
        return {
            "http_status": 400,
            "raw_response": {"error": msg},
            "error_message": msg,
        }

    if selected == "none":
        return {}

    client = get_client()
    t0 = time.perf_counter()

    try:
        status: int
        data: Any

        if selected == "get_member_me":
            status, data = member_tools.get_me()

        elif selected == "get_boards":
            status, data = client.list_boards()
            if (
                BOARD_SCOPE_ONLY
                and TRELLO_BOARD_ID
                and isinstance(data, list)
                and status < 400
            ):
                data = [
                    b
                    for b in data
                    if isinstance(b, dict) and b.get("id") == TRELLO_BOARD_ID
                ]

        elif selected == "get_board":
            status, data = board_tools.get_board(str(tool_input["board_id"]))

        elif selected == "create_board":
            status, data = board_tools.create_board(
                str(tool_input["name"]),
                desc=tool_input.get("desc"),
            )

        elif selected == "update_board":
            fields = {k: v for k, v in tool_input.items() if k not in ("op", "board_id")}
            status, data = board_tools.update_board(str(tool_input["board_id"]), **fields)

        elif selected == "get_lists":
            status, data = board_tools.get_board_lists(str(tool_input["board_id"]))

        elif selected == "create_list":
            status, data = list_tools.create_list(
                str(tool_input["board_id"]),
                str(tool_input["name"]),
            )

        elif selected == "update_list":
            lid = str(tool_input["list_id"])
            fields = {k: v for k, v in tool_input.items() if k not in ("op", "list_id")}
            status, data = list_tools.update_list(lid, **fields)

        elif selected == "archive_list":
            status, data = list_tools.archive_list(str(tool_input["list_id"]), closed=tool_input.get("closed", True))

        elif selected == "get_board_cards":
            bid = str(tool_input["board_id"])
            st, lists = client.get_board_lists(bid)
            if st >= 400:
                return {
                    "http_status": st,
                    "raw_response": lists if isinstance(lists, list) else [],
                    "error_message": f"Trello HTTP {st}",
                }
            all_cards: list[dict[str, Any]] = []
            for lst in lists:
                if not isinstance(lst, dict) or lst.get("closed"):
                    continue
                lid = lst.get("id")
                lname = lst.get("name")
                if not lid:
                    continue
                stc, cards = client.get_list_cards(
                    str(lid),
                    fields="name,id,idList,due,closed",
                )
                if stc >= 400:
                    continue
                for c in cards:
                    if isinstance(c, dict) and not c.get("closed", False):
                        cc = dict(c)
                        cc["_list_name"] = lname
                        all_cards.append(cc)
            status, data = 200, all_cards

        elif selected == "get_cards":
            status, data = client.get_list_cards(
                str(tool_input["list_id"]),
                fields="name,id,idList,due,closed",
            )
            if isinstance(data, list):
                data = [c for c in data if isinstance(c, dict) and not c.get("closed", False)]

        elif selected == "get_card_details":
            status, data = card_tools.get_card_details(str(tool_input["card_id"]))

        elif selected == "create_card":
            status, data = card_tools.create_card(
                str(tool_input["id_list"]),
                str(tool_input["name"]),
                desc=tool_input.get("desc"),
                due=tool_input.get("due"),
            )

        elif selected == "update_card":
            card_id = str(tool_input["card_id"])
            fields = {k: v for k, v in tool_input.items() if k not in ("card_id", "op")}
            status, data = card_tools.update_card(card_id, **fields)

        elif selected == "move_card":
            if tool_input.get("_noop"):
                status, data = 200, {"id": tool_input["card_id"], "idList": tool_input["id_list"], "_noop": True}
            else:
                status, data = card_tools.move_card(
                    str(tool_input["card_id"]),
                    str(tool_input["id_list"]),
                )

        elif selected == "delete_card":
            status, data = card_tools.delete_card(str(tool_input["card_id"]))

        elif selected == "get_card_checklists":
            status, data = card_tools.get_card_checklists(str(tool_input["card_id"]))

        elif selected == "create_checklist":
            status, data = card_tools.post_card_checklist(
                str(tool_input["card_id"]),
                str(tool_input["name"]),
            )

        elif selected == "delete_checklist":
            status, data = checklist_tools.delete_checklist(str(tool_input["checklist_id"]))

        elif selected == "get_checkitems":
            status, data = checklist_tools.get_checkitems(str(tool_input["checklist_id"]))

        elif selected == "create_checkitem":
            status, data = checklist_tools.create_checkitem(
                str(tool_input["checklist_id"]),
                str(tool_input["name"]),
            )

        elif selected in ("check_item", "uncheck_item"):
            status, data = checklist_tools.set_checkitem_state(
                str(tool_input["card_id"]),
                str(tool_input["check_item_id"]),
                str(tool_input["state"]),
            )

        elif selected == "delete_checkitem":
            status, data = checklist_tools.delete_checkitem(
                str(tool_input["checklist_id"]),
                str(tool_input["check_item_id"]),
            )

        elif selected == "get_comments":
            status, data = action_tools.get_card_actions(
                str(tool_input["card_id"]),
                filter="commentCard",
            )

        elif selected == "create_comment":
            status, data = action_tools.post_comment(
                str(tool_input["card_id"]),
                str(tool_input["text"]),
            )

        elif selected == "update_comment":
            status, data = action_tools.update_comment(
                str(tool_input["action_id"]),
                str(tool_input["text"]),
            )

        elif selected == "delete_comment":
            status, data = action_tools.delete_comment(str(tool_input["action_id"]))

        elif selected == "get_board_labels":
            status, data = board_tools.get_board_labels(str(tool_input["board_id"]))

        elif selected == "create_label":
            status, data = board_tools.create_label(
                str(tool_input["board_id"]),
                str(tool_input["name"]),
                color=tool_input.get("color"),
            )

        elif selected == "add_card_label":
            status, data = card_tools.add_label(
                str(tool_input["card_id"]),
                str(tool_input["label_id"]),
            )

        elif selected == "remove_card_label":
            status, data = card_tools.remove_label(
                str(tool_input["card_id"]),
                str(tool_input["label_id"]),
            )

        elif selected == "get_board_members":
            status, data = board_tools.get_board_members(str(tool_input["board_id"]))

        elif selected == "get_board_actions":
            params: dict[str, Any] = {}
            if tool_input.get("filter"):
                params["filter"] = tool_input["filter"]
            status, data = board_tools.get_board_actions(str(tool_input["board_id"]), **params)

        else:
            return {
                "http_status": 400,
                "raw_response": {},
                "error_message": f"Unknown tool {selected}",
            }

        latency_ms = (time.perf_counter() - t0) * 1000
        err = "" if status < 400 else f"Trello HTTP {status}"
        return {
            "http_status": status,
            "raw_response": deepcopy(data) if isinstance(data, (dict, list)) else data,
            "error_message": err,
            "_latency_ms": latency_ms,
        }
    except Exception as e:
        logger.exception("tool_executor")
        return {
            "http_status": 0,
            "raw_response": {},
            "error_message": str(e),
        }
