# Board listing & answer-token fixes (Apr 2026)

## Symptoms

1. **Wrong clarify loop** — For questions like “what boards are available”, “all the board”, “list me all the board”, or Indonesian “saya mau liat semua board”, the graph could still run `board.resolve_board` and end with something like:

   > Which board do you mean? AXA Agency, General, HRGA, …

   even though the user asked for **every** board, not to disambiguate one name.

2. **Answer step 429 (“request too large”)** — After fixing routing, `member.get_my_boards` returned **full** Trello board JSON (limits, prefs, memberships, backgrounds, …). That JSON was passed verbatim into the answer prompt (~hundreds of KB, **~66k tokens**), exceeding org TPM and failing with `RateLimitError`.

## Root causes

| Issue | Cause |
|--------|--------|
| Clarify instead of list | `resolve_board` treated the whole sentence as a **name hint** (e.g. regex captured “that available” from “what are **board** **that available**”) or **singular** “board” didn’t match catalog heuristics that expected “boards”. |
| Huge answer prompt | Plan results and `step_summaries` embedded **unslimmed** `/members/me/boards` payloads. |

## What we changed

### A. Catalog intent in `BoardAgent` (`app/agents/trello/board.py`)

- Added **`_wants_board_catalog()`** — detects list/show/what/which/all/my/every phrasing, **singular** patterns (`all the board`, `list … all … board`), and “available” style questions.
- When catalog intent matches (from `user_text` or `board_hint`), **`resolve_board` returns `ok`** with **`boards`** + **`board_count`**, not **`clarify_user`**.
- Tightened name extraction from free text: quoted names and “board called/named …” only (no greedy `board …` capture).

### B. Orchestrator hint (`app/prompt/orchestrator.py`)

- Catalog flows documented: use **`member.get_my_boards`** or **`board.resolve_board`** with **empty `board_hint`**; do not paste full user sentences into `board_hint`.

### C. Slim payloads for the LLM

- **`app/utils/trello_summaries.py`** — `slim_board`, `slim_boards`, `slim_card(s)`, `slim_result_for_answer`.
- **`MemberAgent.get_my_boards`** — returns **`slim_boards(...)`** so each board is ~`id`, `name`, `closed`, `url`, `starred`, `dateLastActivity`.
- **`plan_executor._aggregate_parsed`** — runs **`slim_result_for_answer`** on each step before building **`step_summaries`** and top-level fields.
- **`BoardAgent`** — successful responses that include a **`board`** object use **`slim_board`** so plans/logs stay small.

### D. Tests

- `tests/test_board_resolve_by_id.py` — catalog phrases, singular “all the board”, `board_id`-only resolve.
- `tests/test_trello_summaries.py` — slimming drops heavy fields.

## Expected behavior now

- **List-all-boards** queries → one step returns a **compact** `boards` array → answer model gets **small** authoritative JSON → natural list reply (not the disambiguation paragraph above).
- If you still see full `nodeId` / `limits` / `prefs` inside answer logs, the running process is on **old code**; redeploy/restart so `slim_*` paths are active.

## Related layout (earlier)

- LangGraph nodes live under **`app/core/nodes/`** (next to **`app/core/graph.py`**).
- Trello specialists live under **`app/agents/trello/`**; orchestrator/answer/bus stay in **`app/agents/`**.
