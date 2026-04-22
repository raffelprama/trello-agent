# 04 — Session memory and governance

Working **memory** carries context across turns (CLI automatically; HTTP when the client echoes the returned `memory`). This doc summarizes structure, finalization, clarification, and safety gates.

## Memory shape and updates

Helpers live in [`../app/session_memory.py`](../app/session_memory.py).

- **`empty_memory()`** — default keys: `board_id`, `board_name`, `list_map`, `last_cards`, focus ids, `custom_field_map`, `webhook_map`, `settings`, `destructive_confirmed_for_plan`, `pending_clarify`, `pending_plan`.
- **`merge_memory`** — shallow merge with nested `settings` merge.
- **`memory_summary_for_planner`** — compact text injected into the orchestrator prompt.
- **`finalize_turn_memory(prev, out)`** — called at end of `invoke_agent` in [`../app/graph.py`](../app/graph.py): merges graph output, handles clarification vs success, updates `pending_plan` / `pending_clarify`.

On **successful** evaluation without clarification errors, memory is enriched via `extract_from_plan_parsed` (and legacy `extract_from_parsed_and_entities` fallback) from `parsed_response` and `entities`.

## Clarification path

When specialists return `clarify_user` or the executor requests **destructive confirmation**, the graph routes to the **`clarify`** node ([`../app/nodes/clarify.py`](../app/nodes/clarify.py)):

- Sets `answer` to the clarification question.
- Merges **`pending_plan_payload`** into memory via `merge_pending_plan` ([`../app/agents/clarification.py`](../app/agents/clarification.py)) so the next turn can **`resume_plan`**.

`finalize_turn_memory` persists `pending_plan` when `needs_clarification` or clarification-shaped `evaluation_result` / `parsed_response` indicate a blocked step.

## Orchestrator resume and destructive confirm

[`../app/nodes/orchestrator_node.py`](../app/nodes/orchestrator_node.py):

- If `pending_plan.awaiting_destructive_confirm` and the user message matches **`user_confirms_destructive`** ([`plan_governance.py`](../app/plan_governance.py)), the plan is re-emitted with `destructive_confirmed_for_plan` set in memory and execution proceeds.
- If the user does not confirm, pending plan may be cleared and a fresh `build_plan` runs.
- Otherwise, if `pending_plan` holds a normal in-progress plan, **`resume_plan`** incorporates the user’s reply.

## Governance reference

[`../app/plan_governance.py`](../app/plan_governance.py) defines:

- **`MUTATING_STEPS`** / **`DESTRUCTIVE_STEPS`** — `(agent, ask)` tuples used for dry run and confirmation.
- **`is_mutating`**, **`is_destructive`**, **`plan_has_destructive`**
- **`effective_dry_run(memory)`** — honors `memory.settings.dry_run` or top-level `dry_run`.
- **`effective_confirm_mutations(memory)`** — default true when unset; reads `memory.settings.confirm_mutations`.

## Environment and product rules

| Mechanism | Purpose |
|-----------|---------|
| **`DELETE_ITEM`** in `.env` | Default `false`; blocks permanent card deletion at the tool layer until enabled ([`../app/config.py`](../app/config.py), README). |
| **`memory.settings.dry_run`** | Skip mutating HTTP; executor returns early with trace (`dry_run_stopped_at`). |
| **`memory.settings.confirm_mutations`** | When true, destructive steps require a yes-style confirmation per plan. |

Idempotency and other protocol details: [`../README.md`](../README.md) “Reasoning / governance” and [`prd_v3.md`](../prd_v3.md) §14.

## Related documents

- [03 — Plans, agents, and execution](03_plans_agents_and_execution.md)
- [02 — Node flows and routing](02_node_flows_and_routing.md)
- [05 — Code quality and observability](05_code_quality_and_observability.md)
