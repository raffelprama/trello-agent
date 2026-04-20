"""tool_executor — HTTP calls via TrelloClient."""

from __future__ import annotations

import logging
import time
from copy import deepcopy
from typing import Any

from app.config import BOARD_SCOPE_ONLY, TRELLO_BOARD_ID
from app.state import ChatState
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

    client = get_client()
    t0 = time.perf_counter()

    try:
        if selected == "get_boards":
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
        elif selected == "get_lists":
            status, data = client.get_board_lists(str(tool_input["board_id"]))
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
                if not isinstance(lst, dict):
                    continue
                lid = lst.get("id")
                lname = lst.get("name")
                if not lid:
                    continue
                stc, cards = client.get_list_cards(str(lid))
                if stc >= 400:
                    continue
                for c in cards:
                    if isinstance(c, dict):
                        cc = dict(c)
                        cc["_list_name"] = lname
                        all_cards.append(cc)
            status, data = 200, all_cards
        elif selected == "get_card_details":
            status, data = client.get_card_details(str(tool_input["card_id"]))
        elif selected == "get_cards":
            status, data = client.get_list_cards(str(tool_input["list_id"]))
        elif selected == "create_card":
            status, data = client.create_card(
                str(tool_input["id_list"]),
                str(tool_input["name"]),
                desc=tool_input.get("desc"),
                due=tool_input.get("due"),
            )
        elif selected == "update_card":
            card_id = str(tool_input["card_id"])
            fields = {k: v for k, v in tool_input.items() if k != "card_id" and k != "op"}
            status, data = client.update_card(card_id, **fields)
        elif selected == "move_card":
            status, data = client.move_card(
                str(tool_input["card_id"]),
                str(tool_input["id_list"]),
            )
        elif selected == "delete_card":
            status, data = client.delete_card(str(tool_input["card_id"]))
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
