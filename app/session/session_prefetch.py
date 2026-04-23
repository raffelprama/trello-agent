"""Optional session warm-up — prefetch boards/lists for AgentContext-lite (PRD §9.1)."""

from __future__ import annotations

import logging
from typing import Any

from app.tools import board as board_tools
from app.tools import member as member_tools

logger = logging.getLogger(__name__)


def run_prefetch(mem: dict[str, Any]) -> dict[str, Any]:
    """Populate list_map / board hints from Trello; best-effort (never raises)."""
    m = dict(mem)
    try:
        st, me = member_tools.get_me()
        if st < 400 and isinstance(me, dict):
            m["member_me_id"] = me.get("id")
            m["member_me_username"] = me.get("username")
    except Exception as e:
        logger.warning("[prefetch] get_me failed: %s", e)

    try:
        st, boards = member_tools.get_my_boards()
        if st >= 400 or not isinstance(boards, list):
            return m
        m["open_boards_preview"] = [{"id": b.get("id"), "name": b.get("name")} for b in boards[:50] if isinstance(b, dict)]
        bid = m.get("board_id")
        if not bid and len(boards) == 1 and isinstance(boards[0], dict):
            bid = boards[0].get("id")
            if bid:
                m["board_id"] = bid
                m["board_name"] = boards[0].get("name")
        if bid:
            st2, lists = board_tools.get_board_lists(str(bid), cards="none")
            if st2 < 400 and isinstance(lists, list):
                m["list_map"] = [{"id": x.get("id"), "name": x.get("name")} for x in lists if isinstance(x, dict) and x.get("id")]
    except Exception as e:
        logger.warning("[prefetch] boards/lists failed: %s", e)
    return m
