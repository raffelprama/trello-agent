"""LangGraph assembly for the Trello agent (A2A: orchestrator → plan_executor → answer | clarify | reflection)."""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from app.core.state import ChatState
from app.session.session_memory import finalize_turn_memory

logger = logging.getLogger(__name__)

_compiled_graph: Any = None


def route_after_orchestrator(state: ChatState) -> Literal["plan_executor", "reflection"]:
    if state.get("skip_tools"):
        return "reflection"
    return "plan_executor"


def route_after_plan_executor(state: ChatState) -> Literal["clarify", "answer_generator", "reflection"]:
    if state.get("needs_clarification"):
        return "clarify"
    if (state.get("plan_execution_status") or "") == "error" or (state.get("error_message") or "").strip():
        return "reflection"
    return "answer_generator"


def route_after_evaluation(_state: ChatState) -> Literal["end"]:
    return "end"


def _build_graph():
    t_build = time.perf_counter()

    def _elapsed() -> float:
        return (time.perf_counter() - t_build) * 1000

    logger.info(
        "[startup] building LangGraph (imports + compile) — watch steps below; "
        "total time is normal on first load (WSL + /mnt/c can be 10–60s)",
    )

    t = time.perf_counter()
    from langgraph.graph import END, StateGraph

    logger.info(
        "[startup] imported langgraph.graph in %.0fms (total %.0fms)",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )

    t = time.perf_counter()
    from app.core.nodes.answer_generator import answer_generator
    from app.core.nodes.clarify import clarify_node
    from app.core.nodes.evaluation import evaluation
    from app.core.nodes.orchestrator_node import orchestrator_node
    from app.core.nodes.plan_executor import plan_executor_node
    from app.core.nodes.reflection import reflection_node

    logger.info(
        "[startup] imported A2A nodes in %.0fms (total %.0fms)",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )

    t = time.perf_counter()
    g = StateGraph(ChatState)
    g.add_node("orchestrator", orchestrator_node)
    g.add_node("plan_executor", plan_executor_node)
    g.add_node("answer_generator", answer_generator)
    g.add_node("evaluation", evaluation)
    g.add_node("reflection", reflection_node)
    g.add_node("clarify", clarify_node)

    g.set_entry_point("orchestrator")
    g.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {"plan_executor": "plan_executor", "reflection": "reflection"},
    )
    g.add_conditional_edges(
        "plan_executor",
        route_after_plan_executor,
        {"clarify": "clarify", "answer_generator": "answer_generator", "reflection": "reflection"},
    )
    g.add_edge("answer_generator", "evaluation")
    g.add_conditional_edges("evaluation", route_after_evaluation, {"end": END})
    g.add_edge("reflection", END)
    g.add_edge("clarify", END)

    logger.info(
        "[startup] wiring nodes/edges done in %.0fms (total %.0fms); compiling…",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )
    t = time.perf_counter()
    compiled = g.compile()
    logger.info(
        "[startup] graph.compile() finished in %.0fms — graph build total %.0fms",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )
    return compiled


def get_compiled_graph():
    """Return compiled graph, building it on first use."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


_first_invoke_complete = False


def invoke_agent(
    question: str,
    history: list[str] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the graph and return final state dict."""
    global _first_invoke_complete
    initial: ChatState = {
        "question": question,
        "history": list(history or []),
        "evaluation_retry_count": 0,
        "memory": dict(memory or {}),
        "needs_clarification": False,
        "clarification_question": "",
        "ambiguous_entities": {},
        "plan": {},
    }
    graph = get_compiled_graph()
    first_turn = not _first_invoke_complete
    if first_turn:
        logger.info(
            "[startup] calling graph.invoke — next logs are orchestrator → plan_executor → "
            "answer; httpx lines are Trello/OpenAI HTTP",
        )
    t_run = time.perf_counter()
    out = graph.invoke(initial)
    od = dict(out)
    mem_in = initial.get("memory") or {}
    od["memory"] = finalize_turn_memory(mem_in if isinstance(mem_in, dict) else {}, od)
    if first_turn:
        ms = (time.perf_counter() - t_run) * 1000
        logger.info(
            "[startup] first graph.invoke completed in %.0fms (end-to-end for this question)",
            ms,
        )
        _first_invoke_complete = True
    return od
