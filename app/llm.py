"""OpenAI chat model factory."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_openai import ChatOpenAI

from app.config import LOG_LLM_FULL, LOG_MAX_BODY_CHARS, MODEL, OPENAI_API_KEY
from app.observability import text_preview

logger = logging.getLogger(__name__)

_chat_model_logged = False


def get_chat_model(temperature: float = 0.0) -> ChatOpenAI:
    """Return a ChatOpenAI instance. First call logs timing (cold import of client stack)."""
    global _chat_model_logged
    t0 = time.perf_counter()
    model = ChatOpenAI(
        model=MODEL,
        api_key=OPENAI_API_KEY,
        temperature=temperature,
    )
    if not _chat_model_logged:
        _chat_model_logged = True
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[startup] first ChatOpenAI constructed (model=%s) in %.0fms — "
            "this and the first HTTP call to OpenAI dominate perceived latency",
            MODEL,
            ms,
        )
    return model


def _format_messages_for_log(messages: list[Any]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > 4000:
                content = content[:4000] + f"... [truncated, {len(content)} chars]"
            parts.append(f"{role}:{content!r}")
        else:
            parts.append(repr(m)[:2000])
    blob = " | ".join(parts)
    return text_preview(blob, max_chars=LOG_MAX_BODY_CHARS)


def _serialize_llm_output(result: Any) -> str:
    if hasattr(result, "model_dump"):
        try:
            return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
        except Exception:
            pass
    if hasattr(result, "content"):
        return str(result.content)
    return repr(result)


def invoke_chat_logged(llm: Any, messages: list[Any], *, operation: str) -> Any:
    """Invoke chat model with timing + optional full I/O when LOG_LLM_FULL=true."""
    t0 = time.perf_counter()
    logger.info("[llm] %s start model=%s", operation, MODEL)
    if LOG_LLM_FULL:
        logger.info("[llm] %s request_messages=%s", operation, _format_messages_for_log(messages))
    try:
        out = llm.invoke(messages)
    except Exception:
        ms = (time.perf_counter() - t0) * 1000
        logger.exception("[llm] %s failed after %.0fms", operation, ms)
        raise
    ms = (time.perf_counter() - t0) * 1000
    text = _serialize_llm_output(out)
    logger.info(
        "[llm] %s done model=%s duration_ms=%.0f response_chars=%d",
        operation,
        MODEL,
        ms,
        len(text),
    )
    if LOG_LLM_FULL:
        logger.info("[llm] %s response=%s", operation, text_preview(text))
    return out
