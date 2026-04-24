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
| [07 — Bulk, scaffold, summarize, done](07_bulk_scaffold_summarize_and_done.md) | Router vs bulk planner, `batch` / `_foreach`, construction agent, board summary, marking done |

## Quick links

- Application README: [../README.md](../README.md)
- Graph assembly: [../app/core/graph.py](../app/core/graph.py)
- Shared state: [../app/core/state.py](../app/core/state.py)

## Package layout (`app/`)

| Folder | Role |
|--------|------|
| `app/core/` | `config.py`, `state.py`, `llm.py`, `graph.py` |
| `app/core/nodes/` | LangGraph nodes: `router_node`, `orchestrator_node`, `bulk_orchestrator_node`, `plan_executor`, `answer_generator`, `evaluation`, `reflection`, `clarify` |
| `app/services/` | Trello HTTP client (`trello_client.py`) |
| `app/session/` | `session_memory.py`, `session_prefetch.py` |
| `app/governance/` | `plan_governance.py`, `intent_taxonomy.py` |
| `app/utils/` | `resolution.py`, `time_context.py`, `trello_summaries.py`, `done_intent.py` |
| `app/observability/` | `logging_setup.py`, `observability.py`, `cli_history.py` |
| `app/prompt/` | `orchestrator.py`, `bulk_orchestrator.py`, `answer.py`, `reflection.py` |
| `app/agents/` | `orchestrator.py`, `bus.py`, `base.py`, `answer.py`, `reflection.py`, `clarification.py` |
| `app/agents/trello/` | Domain specialists: `board`, `list_agent`, `card`, `checklist`, `label`, `comment`, `batch`, `scaffold`, `member`, `search_agent`, etc. |
| `app/tools/` | Low-level Trello REST helpers per resource |

## Topics intentionally not covered

This repo has no **Docker** stack, **Mailgun** notifications, **FAQ/RAG parity** docs, or payment/language-alignment guides. Those appeared in an external reference folder but have no analogue here; the numbering above stops at what exists in `trello_agent`.
