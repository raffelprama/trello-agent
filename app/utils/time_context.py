"""Reference date/time injected into LLM prompts for relative dates and overdue logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import REFERENCE_TIMEZONE


def _effective_timezone_name(mem: dict[str, Any] | None) -> str | None:
    if mem and isinstance(mem.get("settings"), dict):
        raw = mem["settings"].get("timezone")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if REFERENCE_TIMEZONE:
        return REFERENCE_TIMEZONE.strip()
    return None


def format_reference_time_for_prompt(mem: dict[str, Any] | None) -> str:
    """Single block prepended to planner memory and answer prompts.

    Trello returns card ``due`` as ISO 8601 (UTC). Comparisons for overdue should use UTC ``now``.
    Optional ``memory.settings.timezone`` (IANA name, e.g. ``Asia/Jakarta``) adds a local clock line.
    """
    now_utc = datetime.now(timezone.utc)
    utc_s = now_utc.isoformat().replace("+00:00", "Z")
    lines = [
        "Reference time (use for 'today', 'tomorrow', 'overdue', and converting relative dates to ISO 8601 UTC for Trello):",
        f"- Now (UTC): {utc_s}",
    ]
    tz_name = _effective_timezone_name(mem)
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            local = now_utc.astimezone(ZoneInfo(tz_name))
            lines.append(f"- Now (local, {tz_name}): {local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception:
            lines.append(f"- (Could not load timezone {tz_name!r}; use UTC for calendar math.)")
    lines.append(
        "- Overdue rule: a card is overdue only if `due` is non-null, `dueComplete` is false, "
        "and the `due` instant is strictly before now (UTC). If `dueComplete` is true, it is not overdue."
    )
    lines.append(
        "- For setting due dates from phrases like 'tomorrow', compute the calendar date using the "
        "reference line(s) above, then emit ISO 8601 UTC (e.g. end-of-day UTC or noon UTC—be consistent)."
    )
    return "\n".join(lines)
