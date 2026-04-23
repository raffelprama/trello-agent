"""Shared helpers for truncating and redacting log payloads."""

from __future__ import annotations

import json
from typing import Any

from app.core.config import LOG_MAX_BODY_CHARS


def json_preview(obj: Any, max_chars: int | None = None) -> str:
    """Serialize for logs; truncate long payloads."""
    lim = max_chars if max_chars is not None else LOG_MAX_BODY_CHARS
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except TypeError:
        s = repr(obj)
    if len(s) > lim:
        return s[:lim] + f"... [truncated, len={len(s)}]"
    return s


def text_preview(s: str, max_chars: int | None = None) -> str:
    """Plain string truncation for LLM text logs."""
    lim = max_chars if max_chars is not None else LOG_MAX_BODY_CHARS
    if len(s) <= lim:
        return s
    return s[:lim] + f"... [truncated len={len(s)}]"


def redact_query_params(params: dict[str, Any] | None) -> dict[str, Any]:
    """Hide secrets if present in a param dict."""
    if not params:
        return {}
    out = dict(params)
    for k in ("key", "token", "api_key", "access_token"):
        if k in out:
            out[k] = "***"
    return out
