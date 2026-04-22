# 06 — PRD and roadmap index

Product requirements for the Trello agent live at the repository root. Use this index to pick the right document for **behavioral** detail vs **implementation** detail.

## Versions

| File | Role |
|------|------|
| [`../prd_v1.md`](../prd_v1.md) | Early draft. § LangGraph topology describes a **legacy** pipeline (normalize → entity_resolver → tool_router → tool_executor). **Superseded** by the A2A graph in code. |
| [`../prd_v2.md`](../prd_v2.md) | Expanded API hierarchy and chainable interaction model; good background for Trello resource relationships. Some non-goals (e.g. webhooks) have since been implemented — verify against code and v3. |
| [`../prd_v3.md`](../prd_v3.md) | **Current product spec** for capability map, memory, governance (§14), rate limits, testing matrix, etc. Stated to supersede v2 for new work. |

## Implementation source of truth

For **what actually runs**, prefer:

- [`../app/graph.py`](../app/graph.py) — nodes and edges
- [`../app/state.py`](../app/state.py) — `ChatState`
- [`../README.md`](../README.md) — operator setup, env vars, architecture summary
- This `docs/` folder — topology, routing, plans, memory, observability

When PRD text and code disagree, treat **code + these docs** as authoritative unless you are deliberately planning a spec change.

## Related documents

- [01 — Architecture and topology](01_architecture_and_topology.md)
- [05 — Code quality and observability](05_code_quality_and_observability.md)
