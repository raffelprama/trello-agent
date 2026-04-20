"""OpenAI chat model factory."""

from __future__ import annotations

import logging
import time

from langchain_openai import ChatOpenAI

from app.config import MODEL, OPENAI_API_KEY

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
