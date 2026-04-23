# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (inside trello_agent/)
python -m venv .venv
source .venv/bin/activate        # Linux/WSL
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# Run CLI (REPL)
python cli.py --trace            # print plan/intent/eval after each turn
python cli.py --verbose          # DEBUG-level app.* logs on stderr

# Run API
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests — must use the venv's python; system python3 lacks deps
python -m pytest tests/ -q
python -m pytest tests/test_board_resolve_by_id.py -v   # single file
```

**WSL note:** First graph invocation after startup takes 10–60s on `/mnt/c/` paths (import + compile cost). Progress is logged to stderr with `[startup]` prefix.

## Architecture

### Execution path

Both entrypoints (`cli.py` REPL, `main.py` FastAPI) call `invoke_agent()` in `app/core/graph.py`, which runs a compiled LangGraph:

```
router_node ──→ orchestrator_node ──→ plan_executor_node → answer_generator → evaluation → END
            ↘                      ↘ clarify → END        ↘ clarify → END
             → bulk_orchestrator   ↘ reflection → END     ↘ reflection → END
```

- **`router_node`** (`app/core/nodes/router_node.py`): one small LLM call that classifies the request as `"simple"` or `"bulk"`. Resume and destructive-confirm turns skip the LLM entirely (pure state check on `memory.pending_plan`). Returns `task_type` into state.
- **`orchestrator_node`** (`app/core/nodes/orchestrator_node.py`): handles simple tasks — calls `OrchestratorAgent` to either build a new Plan DAG (two LLM calls: `analyze` then `build_plan`) or resume a pending one (`resume_plan`). Also handles destructive-confirm short-circuit and first-turn session prefetch.
- **`bulk_orchestrator_node`** (`app/core/nodes/bulk_orchestrator_node.py`): handles bulk tasks — uses a focused prompt (`app/prompt/bulk_orchestrator.py`) that knows only about `_foreach` and `batch` operations. Produces the same Plan DAG structure as the regular orchestrator.
- **`plan_executor_node`** (`app/core/nodes/plan_executor.py`): walks the Plan DAG step by step, resolves `$step_id.field` references between steps, dispatches each step as an A2A message via `AgentBus`, auto-inserts resolver steps when `need_info` is returned, and handles dry-run and destructive-confirm gating.
- **`answer_generator`** / **`reflection_node`** / **`clarify_node`**: thin wrappers over `AnswerAgent`, `ReflectionAgent`, and clarification persistence.
- **`evaluation`**: deterministic HTTP/error-code classifier, no LLM.

### Plan DAG

`OrchestratorAgent.build_plan()` returns a `Plan` (see `app/agents/base.py`) — a list of `PlanStep` objects. Each step targets one agent + ask with inputs. Steps can reference prior step outputs as `"$s0.board_id"` strings; `plan_executor` resolves these before dispatch.

```python
# Typical step
PlanStep(step_id="s1", agent="card", ask="create_card",
         inputs={"list_id": "$s0.list_id", "card_name": "Buy milk"},
         depends_on=["s0"], outputs=["card_id"])
```

### AgentBus and specialist agents

`AgentBus` (`app/agents/bus.py`) is a name → `BaseAgent` registry. `plan_executor` dispatches `A2AMessage(to=agent_name, ask=method, context={user_text, memory, _resolved_inputs})` and receives `A2AResponse(status, data, missing, clarification, error)`.

Status values: `"ok"`, `"need_info"` (missing inputs — executor may auto-insert a resolver step), `"clarify_user"` (needs human input — plan is paused), `"error"`.

Specialist agents live in `app/agents/trello/`. Each implements `handle(msg: A2AMessage) -> A2AResponse` and calls `app/tools/*` directly.

### Session memory

`memory` dict is the only cross-turn state. The CLI keeps it in process; the HTTP API expects the client to echo it back on each request. Key fields: `board_id`, `list_map`, `last_card_id`, `pending_plan` (paused plan awaiting clarification or destructive confirm), `settings.confirm_mutations`, `settings.dry_run`.

### Prompt layer

`app/prompt/orchestrator.py` contains `ORCHESTRATOR_CATALOG` (the agent/ask list the LLM plans from) and all prompt templates. Changes to agent capabilities must be reflected here or the orchestrator won't use them.

### Slim utilities

`app/utils/trello_summaries.py` — `slim_board`, `slim_boards`, `slim_result_for_answer`. Always use these when returning Trello API payloads from agents; raw `/members/me/boards` responses are ~130KB and will blow past LLM token limits.

## Adding a new agent

1. Create `app/agents/trello/myagent.py`, subclass `BaseAgent`, implement `handle()`.
2. Register in `create_default_bus()` in `app/agents/bus.py`.
3. Add the agent name + ask list to `ORCHESTRATOR_CATALOG` in `app/prompt/orchestrator.py`. If it's bulk-only, also add it to `BULK_CATALOG` in `app/prompt/bulk_orchestrator.py`.
4. If the agent makes mutating Trello calls, add `("myagent", "my_ask")` to `MUTATING_STEPS` in `app/governance/plan_governance.py`.

## Bulk / multi-task operations

Two mechanisms for applying an action to many items:

- **`batch` agent** (`app/agents/trello/batch.py`): handles iteration internally. Plan step: `batch.mark_list_cards_complete(list_id)` or `batch.archive_list_cards(list_id)`. Add new asks here for additional bulk patterns.
- **`_foreach` pseudo-agent**: the plan executor (`plan_executor.py`) expands it at runtime. Plan step inputs: `{"source": "$sX.cards", "item_id_field": "id", "key_as": "card_id", "agent": "card", "ask": "set_card_due_complete", "extra_inputs": {"dueComplete": true}}`. `key_as` defaults to `"card_id"` when `agent == "card"`. `extra_inputs` values must be literals (no `$ref` resolution inside nested dicts).

## Non-obvious behaviors

- **`board_hint` empty string = catalog request**: When the orchestrator sends `board.resolve_board` with `board_hint=""` and no `board_id`, that signals "list all boards". The catalog flow returns `boards` array (slimmed) with status `"ok"`, not `"clarify_user"`. For new "list all boards" intents, always route to `member.get_my_boards` in the orchestrator catalog — never `board.resolve_board`.
- **Name resolution strategy** (`app/utils/resolution.py`): exact → prefix → substring → Levenshtein ≤2 (single candidate only). If two names are within edit distance 2, it clarifies rather than guessing.
- **`BOARD_SCOPE_ONLY`**: defaults `true` when `TRELLO_BOARD_ID` is set. In that mode, `get_boards` returns only the one board and all plans are locked to it.
- **`DELETE_ITEM=false`** blocks `delete_card` entirely (returns error). Set `true` to enable permanent deletion.
- **Two-stage orchestrator**: `analyze()` extracts intent/entities, `build_plan()` synthesizes the DAG. The analysis object is passed into `build_plan` so the planner doesn't re-derive intent. If you bypass `analyze()`, pass `analysis=None` and `build_plan` calls it internally.
- **`pending_plan` in memory** is the serialized Plan DAG. When the next turn arrives with a pending plan, `orchestrator_node` calls `resume_plan()` which patches blocked step inputs based on the user's reply (or abandons and rebuilds).
- **Governance**: `confirm_mutations=true` (default) pauses before destructive steps once per plan ID. `dry_run=true` stops at the first mutating step and returns a partial trace.

## Environment variables

| Variable | Purpose |
|---|---|
| `TRELLO_API_KEY` / `TRELLO_API_TOKEN` | Trello credentials |
| `TRELLO_BOARD_ID` | Default board; enables single-board mode |
| `BOARD_SCOPE_ONLY` | `true` = locked to TRELLO_BOARD_ID |
| `API_KEY` or `OPENAI_API_KEY` | OpenAI key |
| `MODEL` | OpenAI model name (e.g. `gpt-4.1`) |
| `DELETE_ITEM` | `false` (default) blocks card deletion |
| `SESSION_PREFETCH` | `false` (default); prefetches me/boards on first turn |
| `REFERENCE_TIMEZONE` | IANA timezone for relative date resolution |
| `LOG_TRELLO_FULL` | `true` logs full Trello request/response bodies |
| `LOG_LLM_FULL` | `true` logs full LLM prompts and responses |
