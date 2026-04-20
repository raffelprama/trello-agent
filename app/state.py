"""LangGraph shared state (ChatState)."""

from __future__ import annotations

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    """State flowing through the agent graph (PRD §5)."""

    # Input
    question: str
    history: list[str]

    # Planning
    cleaned_query: str
    intent: str
    entities: dict[str, Any]
    reasoning_trace: str

    # Execution
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
