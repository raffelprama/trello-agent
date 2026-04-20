"""evaluation — deterministic success / retry / giveup."""

from __future__ import annotations

from typing import Any

from app.config import MAX_EVAL_RETRIES
from app.state import ChatState


def evaluation(state: ChatState) -> dict[str, Any]:
    http = int(state.get("http_status") or 0)
    err = (state.get("error_message") or "").strip()
    retries = int(state.get("evaluation_retry_count") or 0)

    # Tool path skipped (should not reach here normally)
    if state.get("skip_tools"):
        return {
            "evaluation_result": {"status": "giveup", "reason": "skipped tools"},
            "evaluation_retry_count": retries,
        }

    ok = 200 <= http < 300 if http else False
    if http == 0 and not err:
        # observer-only path
        ok = True

    if ok and not err:
        return {
            "evaluation_result": {"status": "success", "reason": "ok"},
            "evaluation_retry_count": retries,
        }

    # Retrying the same router/executor path will not fix missing entities or client input errors.
    if err and any(
        x in err
        for x in (
            "requires",
            "Missing ",
            "Unknown tool",
            "Unknown routing",
        )
    ):
        return {
            "evaluation_result": {"status": "giveup", "reason": err},
            "evaluation_retry_count": retries + 1,
        }

    if retries < MAX_EVAL_RETRIES:
        return {
            "evaluation_result": {
                "status": "retry",
                "reason": err or f"HTTP {http}",
            },
            "evaluation_retry_count": retries + 1,
        }

    return {
        "evaluation_result": {
            "status": "giveup",
            "reason": err or f"HTTP {http}",
        },
        "evaluation_retry_count": retries + 1,
    }
