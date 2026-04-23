# 05 — Code quality, testing, and observability

## Tests

Tests live under [`../tests/`](../tests/). Examples:

- `test_resolution.py` — name matching / resolution helpers
- `test_session_memory.py` — memory merge and finalize behavior
- `test_plan_governance.py` — mutating/destructive classification and confirm heuristics
- `test_*_agent_*.py`, `test_board_resolve_by_id.py`, `test_member_resolve.py`, `test_checklist_create.py` — specialist and integration-style coverage

Run (from `trello_agent` with dependencies installed):

```bash
python -m pytest tests/ -q
```

Also documented in [`../README.md`](../README.md).

## Logging

[`../app/logging_setup.py`](../app/logging_setup.py):

- **`setup_logging`** — stderr stream, format `%(asctime)s | %(levelname)s | %(name)s | %(message)s`.
- **`log_event(logger, request_id, event, **fields)`** — structured key=value lines for HTTP handlers.
- **`new_request_id()`** — UUID for per-request correlation.

CLI **`--verbose`** sets `app.*` loggers to **DEBUG** for noisier startup and node detail.

## Payload hygiene

[`../app/observability.py`](../app/observability.py):

- **`json_preview`**, **`text_preview`** — truncate serialized payloads using `LOG_MAX_BODY_CHARS` from config.
- **`redact_query_params`** — masks `key`, `token`, `api_key`, `access_token` in dicts logged from Trello calls.

## Runtime log families

Described in [`../README.md`](../README.md) “Observability (stderr)”:

| Prefix | Source |
|--------|--------|
| `[trello]` | Trello HTTP client (method, path, status, duration, size) |
| `[llm]` | LLM invocations (`orchestrator_build_plan`, `answer_agent`, …) |
| `[a2a]` | AgentBus dispatch / reply |
| `[plan]` | Plan build / step execution |
| `[startup]` | LangGraph import and compile timing |

Flags **`LOG_TRELLO_FULL`** and **`LOG_LLM_FULL`** opt into fuller bodies (still truncated).

## API trace

[`../main.py`](../main.py) builds `ChatResponse.trace` from the final graph state:

- `retries`, `tool`, `evaluation` status/reason
- `plan_id`, last `plan_step`, `plan_agent`, `plan_status`
- Full **`plan_trace`** list (per-step status; steps may include `http` arrays from Trello when available)

Clients can log or persist this for debugging without enabling full body logging.

## Evaluation node

[`../app/core/nodes/evaluation.py`](../app/core/nodes/evaluation.py) runs after **`answer_generator`** on the happy path:

- Treats **HTTP 2xx** (when `http_status` set) or **observer-only** path (`http_status==0` and no error) as success.
- **`giveup`** for certain error substrings (`requires`, `Missing `, `Unknown tool`, `Unknown routing`) without wasting retries.
- Otherwise **`retry`** while `evaluation_retry_count < MAX_EVAL_RETRIES` (`config.MAX_EVAL_RETRIES`, default `2`), then **`giveup`**.

There is no graph edge that loops back from `evaluation` into the executor today; retries are reflected in `evaluation_result` for observability.

## Related documents

- [02 — Node flows and routing](02_node_flows_and_routing.md)
- [01 — Architecture and topology](01_architecture_and_topology.md)
