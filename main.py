"""FastAPI entrypoint — stateless POST /chat."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.core.graph import invoke_agent
from app.observability.logging_setup import log_event, new_request_id, setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Trello AI Agent", version="0.1.0")


class ChatRequest(BaseModel):
    question: str
    auth: str | None = Field(
        default=None,
        description="Reserved for future per-user credentials; ignored in MVP.",
    )
    history: list[str] | None = Field(
        default=None,
        description="Optional prior turns (oldest first), client-managed.",
    )
    memory: dict | None = Field(
        default=None,
        description="Optional session working memory (board_id, last_cards, etc.).",
    )
    id: UUID | None = Field(default=None, description="Correlation id; echoed back.")


class ChatResponse(BaseModel):
    id: UUID
    answer: str
    intent: str | None = None
    trace: dict = Field(default_factory=dict)
    memory: dict | None = None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    rid = req.id or uuid4()
    log_id = new_request_id()
    log_event(logger, log_id, "chat_start", request_id=str(rid), question_len=len(req.question))

    out = invoke_agent(req.question, req.history, memory=req.memory)

    intent = out.get("intent")
    ev = out.get("evaluation_result") or {}
    pt = out.get("plan_trace") or []
    last_step = pt[-1] if isinstance(pt, list) and pt else {}
    trace = {
        "retries": out.get("evaluation_retry_count", 0),
        "tool": out.get("selected_tool"),
        "evaluation": ev.get("status"),
        "reason": ev.get("reason"),
        "plan_id": (out.get("parsed_response") or {}).get("plan_id") if isinstance(out.get("parsed_response"), dict) else None,
        "plan_step": last_step.get("step_id") if isinstance(last_step, dict) else None,
        "plan_agent": last_step.get("agent") if isinstance(last_step, dict) else None,
        "plan_status": last_step.get("status") if isinstance(last_step, dict) else None,
        "plan_trace": pt,
    }
    log_event(logger, log_id, "chat_end", request_id=str(rid), intent=intent, evaluation=ev.get("status"))

    return ChatResponse(
        id=rid,
        answer=out.get("answer") or "",
        intent=intent if isinstance(intent, str) else None,
        trace=trace,
        memory=out.get("memory"),
    )
