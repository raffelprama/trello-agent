"""Structured logging for requests and graph steps."""

from __future__ import annotations

import logging
import sys
import uuid
from typing import Any

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO, *, verbose: bool = False) -> None:
    """Configure root logging. Logs go to stderr so they stay separate from REPL stdout.

    With ``verbose=True``, ``app.*`` loggers use DEBUG (node-level detail during startup).
    """
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(handler)
    root.setLevel(level)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.DEBUG if verbose else logging.INFO)


def new_request_id() -> str:
    return str(uuid.uuid4())


def log_event(logger: logging.Logger, request_id: str, event: str, **fields: Any) -> None:
    extra = " ".join(f"{k}={v!r}" for k, v in sorted(fields.items()) if v is not None)
    logger.info("[%s] %s %s", request_id, event, extra)
