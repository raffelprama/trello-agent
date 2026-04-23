"""LangGraph shared state (ChatState)."""

from __future__ import annotations

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    """State flowing through the agent graph (A2A + PRD v2)."""

    # Input
    question: str
    history: list[str]

    # Legacy planning fields (optional; kept for API/trace compatibility)
    cleaned_query: str
    intent: str
    entities: dict[str, Any]
    reasoning_trace: str

    # A2A plan DAG
    plan: dict[str, Any]
    plan_trace: list[dict[str, Any]]
    plan_execution_status: str
    pending_plan_payload: dict[str, Any]

    # Clarification
    needs_clarification: bool
    clarification_question: str
    ambiguous_entities: dict[str, Any]
    pending_op: dict[str, Any]

    # Session working memory (cross-turn; CLI injects)
    memory: dict[str, Any]

    # Legacy execution fields (optional)
    selected_tool: str
    tool_input: dict[str, Any]
    http_status: int
    raw_response: Any
    parsed_response: dict[str, Any]

    # Output
    answer: str

    # Evaluation
    evaluation_result: dict[str, Any]
    evaluation_retry_count: int
    error_message: str

    # Internal routing / timing
    skip_tools: bool
    _latency_ms: float
