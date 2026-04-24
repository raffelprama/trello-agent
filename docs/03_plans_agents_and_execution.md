# 03 — Plans, agents, and execution

This document covers **intent chaining** in the Trello agent: planners emit a **Plan** (DAG of steps), `plan_executor` walks it and dispatches **A2A** messages to specialists, and results flow into the answer path.

## Simple vs bulk planning

Two LangGraph nodes can produce a plan; **one** executor runs both:

| Entry | Node | LLM / prompts | Typical use |
|-------|------|-----------------|-------------|
| **Simple** | [`orchestrator_node`](../app/core/nodes/orchestrator_node.py) | [`OrchestratorAgent`](../app/agents/orchestrator.py) + [`app/prompt/orchestrator.py`](../app/prompt/orchestrator.py) | Single actions, queries, short chains, scaffold/summarize/move one card, etc. |
| **Bulk** | [`bulk_orchestrator_node`](../app/core/nodes/bulk_orchestrator_node.py) | Same `_BuildPlan` schema; [`app/prompt/bulk_orchestrator.py`](../app/prompt/bulk_orchestrator.py) | Same operation over many cards/lists (mark all complete, archive all, create many cards, etc.) |

The [**router**](../app/core/nodes/router_node.py) sets `task_type` so [`graph.py`](../app/core/graph.py) `route_after_router` sends the turn to the correct planner. Resume and destructive-confirm turns force **`simple`** so `resume_plan` stays on the standard orchestrator path.

Detail: [07 — Bulk, scaffold, summarize, done](07_bulk_scaffold_summarize_and_done.md).

## Plan DAG

The **OrchestratorAgent** (and bulk planner) produce a structured plan via LLM (`build_plan` / `resume_plan`). Each step includes:

- **`step_id`** — stable id for result references
- **`agent`** — target specialist name (e.g. `board`, `card`, `batch`, `scaffold`) or the pseudo-agent `_foreach`
- **`ask`** — operation name (e.g. `resolve_board`, `move_card`, `create_cards`, `apply`)
- **`inputs`** — dict; values may reference prior step outputs
- **`depends_on`** — list of `step_id`s that must complete first
- **`outputs`** — declared output fields (documentation / consistency for the LLM)

Planners **do not** call Trello; they only emit the plan. Execution is entirely in [`../app/core/nodes/plan_executor.py`](../app/core/nodes/plan_executor.py).

### Reference resolution

Inside `plan_executor`:

- **`$<step_id>.<field>`** — resolved via `parse_ref` against accumulated `plan.results`
- **`$PREV.board_id`** — substituted with the latest `board_id` from results or session memory

Inputs are merged with **`memory`** when `board_id` is missing for list/card-style steps (see executor loop).

### Dependency order

Before each step runs, `_deps_satisfied` ensures every id in `depends_on` exists in `results`. Unsatisfied dependencies return `plan_execution_status: "error"` and route to **reflection** (see [02](02_node_flows_and_routing.md)).

### Aggregated payload

On success, `_aggregate_parsed` builds a **`parsed_response`** shaped like legacy tool output: `plan_id`, `final_intent`, `step_summaries`, plus merged keys such as `queried_board`, `cards`, `lists`, `card`, etc. That dict feeds **AnswerAgent** and session memory extraction.

## AgentBus and dispatch

[`../app/agents/bus.py`](../app/agents/bus.py) registers specialists and implements **`dispatch(A2AMessage) -> A2AResponse`**.

- **Log prefix:** `[a2a]` on dispatch (task, from, to, ask, input preview) and reply (status, data keys, duration).
- **Default registry** (`create_default_bus`): `member`, `board`, `list`, `card`, `checklist`, `label`, `comment`, `custom_field`, `webhook`, `organization`, `search`, `notification`, `attachment`, **`batch`**, **`scaffold`**.

Unknown `msg.to` returns `status="error"` with a clear message.

## Pseudo-agent `_foreach`

**Not** registered on the bus. When `step.agent == "_foreach"`, [`plan_executor`](../app/core/nodes/plan_executor.py) iterates a resolved **`source`** list and dispatches **`agent` / `ask`** once per item with **`key_as`** (e.g. `card_id`) and literal **`extra_inputs`**. See [07](07_bulk_scaffold_summarize_and_done.md) for fields and constraints.

## Specialist response statuses

The executor loop branches on `A2AResponse.status`:

| Status | Executor behavior |
|--------|---------------------|
| `ok` | Store `resp.data` under `step_id`, advance `current_index` |
| `need_info` | Merge missing fields from memory / results; optional redispatch; or insert auto resolve step (`resolve_board` / `resolve_list` / `resolve_card`); or return error with `Missing: ...` |
| `clarify_user` | Set `needs_clarification`, `pending_plan_payload`, `plan_execution_status: "clarify"` → **clarify** node |
| `error` | Set `plan_execution_status: "error"`, `error_message`, HTTP-style status → **reflection** |

## Orchestrator node (LangGraph)

[`../app/core/nodes/orchestrator_node.py`](../app/core/nodes/orchestrator_node.py):

- Optionally runs **session prefetch** when `SESSION_PREFETCH` is true and memory is not yet prefetched (`run_prefetch`).
- Applies **`apply_done_intent_heuristic`** after analyze ([`app/utils/done_intent.py`](../app/utils/done_intent.py)) to reduce false “move vs mark complete” clarification.
- Reads **`memory.pending_plan`** for **resume** (`resume_plan`) or **destructive confirmation** (user must confirm with yes-style text; see [`plan_governance.py`](../governance/plan_governance.py)).
- On failure, returns `skip_tools=True` (and not `needs_clarification`) so routing sends the turn to **reflection** without executing the plan.
- Can return **`needs_clarification`** with **`skip_tools=True`** for intent ambiguity → **clarify** node (see [02](02_node_flows_and_routing.md)).

## Governance hooks in the executor

Before dispatch, the executor checks [`../app/governance/plan_governance.py`](../app/governance/plan_governance.py):

- **Destructive steps** — if `effective_confirm_mutations(memory)` and the step is in `DESTRUCTIVE_STEPS`, execution pauses with a confirmation question and `awaiting_destructive_confirm` on the pending payload unless `destructive_confirmed_for_plan` matches the current `plan_id`.
- **Dry run** — if `effective_dry_run(memory)` and the step is mutating, execution stops with `dry_run_stopped_at` in `parsed_response` and a successful HTTP-style outcome for tracing (no mutating Trello call).

## Related documents

- [02 — Node flows and routing](02_node_flows_and_routing.md)
- [04 — Session memory and governance](04_session_memory_and_governance.md)
- [01 — Architecture and topology](01_architecture_and_topology.md)
- [07 — Bulk, scaffold, summarize, done](07_bulk_scaffold_summarize_and_done.md)
