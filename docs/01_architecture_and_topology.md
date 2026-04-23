# 01 — Architecture and topology

This document describes how the Trello agent is assembled: clients, the LangGraph runtime, specialist agents, HTTP tools, and external APIs.

> **Historical note:** [`prd_v1.md`](../prd_v1.md) describes an older LangGraph topology (entity resolver → tool router → tool executor). The **current** system is the **A2A** pipeline documented here and in [`../README.md`](../README.md). Prefer this doc, `02_node_flows_and_routing.md`, and `graph.py` as the source of truth.

## External topology

Requests enter through either the **HTTP API** or the **CLI**. Both call the same compiled LangGraph via `invoke_agent` in [`../app/graph.py`](../app/graph.py). Specialists perform work by calling **Trello REST API v1** through [`../app/trello_client.py`](../app/trello_client.py) and thin wrappers under [`../app/tools/`](../app/tools/).

```mermaid
flowchart TD
    HttpClient[HTTP POST /chat] -->|optional history + memory| FastAPI[FastAPI main.py]
    Repl[CLI cli.py] --> LangGraph[LangGraph compiled graph]
    FastAPI --> LangGraph
    LangGraph --> OpenAI[OpenAI chat API]
    LangGraph --> TrelloAPI[Trello REST API]
```

- **`main.py`:** `POST /chat` accepts `question`, optional `history`, optional `memory`, optional correlation `id`. Returns `answer`, `intent`, `trace`, and updated `memory`.
- **`cli.py`:** REPL with in-process history and memory; invokes the same graph.

The HTTP surface is **stateless** except for the `memory` dict the client sends and receives. The CLI persists session context in memory across turns.

## Logical layers

| Layer | Location | Role |
|--------|-----------|------|
| **Graph nodes** | [`app/core/nodes/`](../app/core/nodes/) | LangGraph steps: orchestrator, plan executor, answer, evaluation, reflection, clarify |
| **Orchestration LLM** | [`app/agents/orchestrator.py`](../app/agents/orchestrator.py) | Builds or resumes a **Plan** (DAG of steps); does not call Trello |
| **Specialist agents** | [`app/agents/*.py`](../app/agents/) | `handle(A2AMessage) -> A2AResponse`; board, list, card, checklist, etc. |
| **Agent bus** | [`app/agents/bus.py`](../app/agents/bus.py) | Registry and `dispatch` with structured `[a2a]` logging |
| **Trello tools** | [`app/tools/`](../app/tools/) | HTTP verbs and paths for Trello resources |
| **Client** | [`app/trello_client.py`](../app/trello_client.py) | Auth query params, timeouts, rate limiting, retries, HTTP trace consumption |

There is **no** monolithic entity-resolver or tool-router node in the current graph. Resolution and tool choice live inside **specialists** and **orchestrator-produced plan steps**.

## LangGraph topology (high level)

```mermaid
flowchart TD
    Start([START]) --> Orch[orchestrator_node]
    Orch --> RouteO{skip_tools?}
    RouteO -->|yes| Reflection[reflection_node]
    RouteO -->|no| PE[plan_executor]
    PE --> RoutePE{route}
    RoutePE -->|clarify_user| Clarify[clarify]
    RoutePE -->|error| Reflection
    RoutePE -->|ok| AnswerGen[answer_generator]
    AnswerGen --> Evaluation[evaluation]
    Evaluation --> EndSuccess([END])
    Reflection --> EndReflect([END])
    Clarify --> EndClarify([END])
    PE -.-> Bus[AgentBus dispatch]
    Bus -.-> Trello[(Trello API)]
```

See [02 — Node flows and routing](02_node_flows_and_routing.md) for exact routing predicates and state fields.

## Configuration surface

[`../app/config.py`](../app/config.py) loads `.env` from the `trello_agent` directory. Notable settings:

| Setting | Purpose |
|---------|---------|
| `TRELLO_API_KEY` / `TRELLO_KEY` / `TRELOO_KEY` | Trello API key (first non-empty wins) |
| `TRELLO_API_TOKEN` / `TRELLO_TOKEN` | Trello token |
| `TRELLO_BOARD_ID` | Optional default board |
| `BOARD_SCOPE_ONLY` | When `TRELLO_BOARD_ID` is set, default restricts listing to that board |
| `API_KEY` / `OPENAI_API_KEY` | OpenAI credentials |
| `MODEL` | Chat model name (default `gpt-4.1`) |
| `MAX_EVAL_RETRIES` | Evaluation retry budget (default `2`) |
| `DELETE_ITEM` | Must be `true` to allow permanent card delete via API |
| `SESSION_PREFETCH` | First-turn warm-up (`me`, boards, list map) when `true` |
| `LOG_TRELLO_FULL`, `LOG_LLM_FULL`, `LOG_MAX_BODY_CHARS` | Verbose logging and truncation |

Full setup and observability notes: [`../README.md`](../README.md).

## Related documents

- [02 — Node flows and routing](02_node_flows_and_routing.md)
- [03 — Plans, agents, and execution](03_plans_agents_and_execution.md)
