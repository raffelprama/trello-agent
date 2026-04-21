"""Load environment and expose settings for Trello + OpenAI."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from trello_agent directory (parent of app/)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


def _get_trello_key() -> str:
    key = os.getenv("TRELLO_KEY") or os.getenv("TRELOO_KEY")
    if not key:
        raise RuntimeError("Set TRELLO_KEY or TRELOO_KEY in .env")
    return key


def _get_openai_key() -> str:
    key = os.getenv("API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set API_KEY or OPENAI_API_KEY in .env")
    return key


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


TRELLO_KEY: str = _get_trello_key()
TRELLO_TOKEN: str = os.getenv("TRELLO_TOKEN") or ""
if not TRELLO_TOKEN:
    raise RuntimeError("Set TRELLO_TOKEN in .env")

TRELLO_BOARD_ID: str | None = os.getenv("TRELLO_BOARD_ID") or None

# When TRELLO_BOARD_ID is set, restrict the agent to that board only (default True).
# Set BOARD_SCOPE_ONLY=false to list and use other boards even if TRELLO_BOARD_ID is set.
BOARD_SCOPE_ONLY: bool = _env_bool("BOARD_SCOPE_ONLY", default=bool(TRELLO_BOARD_ID))

OPENAI_API_KEY: str = _get_openai_key()
MODEL: str = os.getenv("MODEL", "gpt-4.1")

TRELLO_BASE_URL: str = "https://api.trello.com/1"
HTTP_TIMEOUT_SECONDS: float = 10.0

# Graph evaluation
MAX_EVAL_RETRIES: int = 2

# Destructive actions (DELETE /1/cards/{id}); off by default
DELETE_ITEM: bool = _env_bool("DELETE_ITEM", False)

# Observability — every turn logs Trello + LLM at INFO (summary). Set true for full JSON/text bodies in logs.
LOG_TRELLO_FULL: bool = _env_bool("LOG_TRELLO_FULL", False)
LOG_LLM_FULL: bool = _env_bool("LOG_LLM_FULL", False)
# Max characters when logging full bodies (avoid huge stderr)
LOG_MAX_BODY_CHARS: int = int(os.getenv("LOG_MAX_BODY_CHARS", "16000"))
