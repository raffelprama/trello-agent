"""CLI-only in-memory history + JSONL append for replay/training."""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

MAX_TURNS = 20
_MAX_LINES = MAX_TURNS * 2

_history: dict[str, deque[tuple[str, str]]] = {}
_lock = threading.Lock()

_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "cli_history.log"


def _ensure_session(session_id: str) -> deque[tuple[str, str]]:
    with _lock:
        if session_id not in _history:
            _history[session_id] = deque(maxlen=_MAX_LINES)
        return _history[session_id]


def append_turn(session_id: str, role: str, content: str) -> None:
    d = _ensure_session(session_id)
    d.append((role, content))
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": session_id,
            "role": role,
            "content": content,
        },
        ensure_ascii=False,
    )
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_history_lines(session_id: str) -> list[str]:
    """Format for invoke_agent: list of prior turns as strings."""
    lines: list[str] = []
    for role, content in _ensure_session(session_id):
        lines.append(f"{role}: {content}")
    return lines


def clear_history(session_id: str) -> None:
    with _lock:
        _history.pop(session_id, None)


def format_history_for_display(session_id: str) -> str:
    parts = []
    for role, content in _ensure_session(session_id):
        parts.append(f"[{role}] {content}")
    return "\n".join(parts) if parts else "(empty)"
