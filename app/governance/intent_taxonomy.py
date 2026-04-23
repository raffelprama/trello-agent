"""PRD §7 intent IDs — hints for orchestrator and API normalization (lightweight §8 stand-in)."""

from __future__ import annotations

import re

# Representative v3 intent labels (extend as product defines §7 fully).
KNOWN_INTENTS: frozenset[str] = frozenset(
    {
        "QUERY_BOARDS",
        "QUERY_BOARD",
        "QUERY_CARDS",
        "QUERY_SEARCH",
        "QUERY_NOTIFICATIONS",
        "QUERY_CUSTOM_FIELDS",
        "QUERY_ORGANIZATIONS",
        "CARD_CREATE",
        "CARD_UPDATE",
        "CARD_MOVE",
        "CARD_SET_DUE_COMPLETE",
        "CARD_ARCHIVE",
        "CARD_DELETE",
        "LIST_CREATE",
        "LIST_UPDATE",
        "BOARD_CREATE",
        "BOARD_UPDATE",
        "BOARD_DELETE",
        "CUSTOM_FIELD_SET",
        "CUSTOM_FIELD_CREATE",
        "WEBHOOK_CREATE",
        "WEBHOOK_DELETE",
        "ATTACHMENT_ADD_URL",
        "MEMBER_UPDATE",
    }
)


def normalize_intent_label(raw: str | None) -> str:
    """Uppercase snake-ish token; fall back to QUERY_BOARDS for empty unknown."""
    if not raw or not str(raw).strip():
        return "UNKNOWN"
    s = str(raw).strip().upper()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^A-Z0-9_]", "", s)
    if s in KNOWN_INTENTS:
        return s
    if s.startswith("QUERY_") or s.startswith("CARD_") or s.startswith("BOARD_"):
        return s
    return s if len(s) <= 64 else s[:64]
