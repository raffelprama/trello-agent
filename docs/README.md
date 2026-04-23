# Trello agent documentation

Start here for architecture, LangGraph routing, plan execution, and operations.

## Guides (numbered)

| Doc | Topic |
|-----|--------|
| [01 — Architecture and topology](01_architecture_and_topology.md) | System layers, entrypoints, Trello/OpenAI integration |
| [02 — Node flows and routing](02_node_flows_and_routing.md) | LangGraph nodes, conditional edges, `ChatState` routing |
| [03 — Plans, agents, and execution](03_plans_agents_and_execution.md) | Plan DAG, `$step.field` refs, AgentBus, specialists |
| [04 — Session memory and governance](04_session_memory_and_governance.md) | Working memory, clarification, dry run, destructive confirm |
| [05 — Code quality and observability](05_code_quality_and_observability.md) | Tests, logging, API trace, evaluation node |
| [06 — PRD index](06_prd_and_roadmap_index.md) | Which PRD version matches the current graph |

## Quick links

- Application README: [../README.md](../README.md)
- Graph assembly: [../app/core/graph.py](../app/core/graph.py) (import via `app.graph` shim)
- Shared state: [../app/core/state.py](../app/core/state.py) (import via `app.state` shim)

## Package layout (`app/`)

| Folder | Role |
|--------|------|
| `app/core/` | `config`, `state`, `llm`, `graph` |
| `app/services/` | Trello HTTP client |
| `app/session/` | `session_memory`, `session_prefetch` |
| `app/governance/` | `plan_governance`, `intent_taxonomy` |
| `app/utils/` | `resolution`, `time_context` |
| `app/observability/` | `logging_setup`, `observability`, `cli_history` |
| `app/agents/`, `app/agents/trello/`, `app/tools/`, `app/core/nodes/`, `app/prompt/` | Layout |
| `app/*.py` at root | Thin shims re-exporting the above for stable imports |

## Topics intentionally not covered

This repo has no **Docker** stack, **Mailgun** notifications, **FAQ/RAG parity** docs, or payment/language-alignment guides. Those appeared in an external reference folder but have no analogue here; the numbering above stops at what exists in `trello_agent`.
