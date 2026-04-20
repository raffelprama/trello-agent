"""LangGraph assembly for the Trello agent.

Heavy imports (langgraph, nodes, langchain) load only on first invoke — not at import time.
This keeps CLI startup fast so the REPL prompt appears immediately.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from app.state import ChatState

logger = logging.getLogger(__name__)

_compiled_graph: Any = None


def route_after_planner(state: ChatState) -> Literal["entity_resolver", "reflection"]:
    if state.get("skip_tools"):
        return "reflection"
    return "entity_resolver"


def route_after_entity(state: ChatState) -> Literal["tool_router", "reflection"]:
    if state.get("skip_tools"):
        return "reflection"
    return "tool_router"


def route_after_evaluation(state: ChatState) -> Literal["tool_router", "reflection", "end"]:
    ev = state.get("evaluation_result") or {}
    status = ev.get("status")
    if status == "success":
        return "end"
    if status == "retry":
        return "tool_router"
    return "reflection"


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

    # Import order: heavy LangChain nodes first so logs show where time goes.
    t = time.perf_counter()
    from app.nodes.planner import normalize_intent_planner

    logger.info(
        "[startup] imported planner (pulls LangChain + OpenAI) in %.0fms (total %.0fms)",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )

    t = time.perf_counter()
    from app.nodes.answer_generator import answer_generator
    from app.nodes.reflection import reflection_node

    logger.info(
        "[startup] imported answer_generator + reflection in %.0fms (total %.0fms)",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )

    t = time.perf_counter()
    from app.nodes.entity_resolver import entity_resolver
    from app.nodes.evaluation import evaluation
    from app.nodes.tool_executor import tool_executor
    from app.nodes.tool_observer import tool_observer
    from app.nodes.tool_router import tool_router

    logger.info(
        "[startup] imported entity_resolver, tools, evaluation in %.0fms (total %.0fms)",
        (time.perf_counter() - t) * 1000,
        _elapsed(),
    )

    t = time.perf_counter()
    g = StateGraph(ChatState)
    g.add_node("planner", normalize_intent_planner)
    g.add_node("entity_resolver", entity_resolver)
    g.add_node("tool_router", tool_router)
    g.add_node("tool_executor", tool_executor)
    g.add_node("tool_observer", tool_observer)
    g.add_node("answer_generator", answer_generator)
    g.add_node("evaluation", evaluation)
    g.add_node("reflection", reflection_node)

    g.set_entry_point("planner")
    g.add_conditional_edges(
        "planner",
        route_after_planner,
        {"entity_resolver": "entity_resolver", "reflection": "reflection"},
    )
    g.add_conditional_edges(
        "entity_resolver",
        route_after_entity,
        {"tool_router": "tool_router", "reflection": "reflection"},
    )
    g.add_edge("tool_router", "tool_executor")
    g.add_edge("tool_executor", "tool_observer")
    g.add_edge("tool_observer", "answer_generator")
    g.add_edge("answer_generator", "evaluation")
    g.add_conditional_edges(
        "evaluation",
        route_after_evaluation,
        {"end": END, "tool_router": "tool_router", "reflection": "reflection"},
    )
    g.add_edge("reflection", END)

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
) -> dict[str, Any]:
    """Run the graph and return final state dict."""
    global _first_invoke_complete
    initial: ChatState = {
        "question": question,
        "history": list(history or []),
        "evaluation_retry_count": 0,
    }
    graph = get_compiled_graph()
    first_turn = not _first_invoke_complete
    if first_turn:
        logger.info(
            "[startup] calling graph.invoke — next logs are planner → entity_resolver → "
            "tools → answer_generator; httpx lines are Trello/OpenAI HTTP",
        )
    t_run = time.perf_counter()
    out = graph.invoke(initial)
    if first_turn:
        ms = (time.perf_counter() - t_run) * 1000
        logger.info(
            "[startup] first graph.invoke completed in %.0fms (end-to-end for this question)",
            ms,
        )
        _first_invoke_complete = True
    return dict(out)
