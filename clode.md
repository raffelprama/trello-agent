# CLAUDE.md
    2
    3 This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
    4
    5 ## Commands
    6
    7 ```bash
    8 # Setup (inside trello_agent/)
    9 python -m venv .venv
   10 source .venv/bin/activate        # Linux/WSL
   11 # .venv\Scripts\activate         # Windows
   12 pip install -r requirements.txt
   13
   14 # Run CLI (REPL)
   15 python cli.py --trace            # print plan/intent/eval after each turn
   16 python cli.py --verbose          # DEBUG-level app.* logs on stderr
   17
   18 # Run API
   19 uvicorn main:app --reload --host 0.0.0.0 --port 8000
   20
   21 # Tests — must use the venv's python; system python3 lacks deps
   22 python -m pytest tests/ -q
   23 python -m pytest tests/test_board_resolve_by_id.py -v   # single file
   24 ```
   25
   26 **WSL note:** First graph invocation after startup takes 10–60s on `/mnt/c/` paths (import + compile cost).    
      Progress is logged to stderr with `[startup]` prefix.
   27
   28 ## Architecture
   29
   30 ### Execution path
   31
   32 Both entrypoints (`cli.py` REPL, `main.py` FastAPI) call `invoke_agent()` in `app/core/graph.py`, which runs   
       a compiled LangGraph:
   33
   34 ```
   35 orchestrator_node → plan_executor_node → answer_generator → evaluation → END
   36                  ↘ clarify → END       ↘ clarify → END
   37                  ↘ reflection → END    ↘ reflection → END
   38 ```
   39
   40 - **`orchestrator_node`** (`app/core/nodes/orchestrator_node.py`): calls `OrchestratorAgent` to either build   
       a new Plan DAG (two LLM calls: `analyze` then `build_plan`) or resume a pending one (`resume_plan`). Also h   
      andles destructive-confirm short-circuit and first-turn session prefetch.
   41 - **`plan_executor_node`** (`app/core/nodes/plan_executor.py`): walks the Plan DAG step by step, resolves `$   
      step_id.field` references between steps, dispatches each step as an A2A message via `AgentBus`, auto-inserts   
       resolver steps when `need_info` is returned, and handles dry-run and destructive-confirm gating.
   42 - **`answer_generator`** / **`reflection_node`** / **`clarify_node`**: thin wrappers over `AnswerAgent`, `Re   
      flectionAgent`, and clarification persistence.
   43 - **`evaluation`**: deterministic HTTP/error-code classifier, no LLM.
   44
   45 ### Plan DAG
   46
   47 `OrchestratorAgent.build_plan()` returns a `Plan` (see `app/agents/base.py`) — a list of `PlanStep` objects.   
       Each step targets one agent + ask with inputs. Steps can reference prior step outputs as `"$s0.board_id"` s   
      trings; `plan_executor` resolves these before dispatch.
   48
   49 ```python
   50 # Typical step
   51 PlanStep(step_id="s1", agent="card", ask="create_card",
   52          inputs={"list_id": "$s0.list_id", "card_name": "Buy milk"},
   53          depends_on=["s0"], outputs=["card_id"])
   54 ```
   55
   56 ### AgentBus and specialist agents
   57
   58 `AgentBus` (`app/agents/bus.py`) is a name → `BaseAgent` registry. `plan_executor` dispatches `A2AMessage(to   
      =agent_name, ask=method, context={user_text, memory, _resolved_inputs})` and receives `A2AResponse(status, d   
      ata, missing, clarification, error)`.
   59
   60 Status values: `"ok"`, `"need_info"` (missing inputs — executor may auto-insert a resolver step), `"clarify_   
      user"` (needs human input — plan is paused), `"error"`.
   61
   62 Specialist agents live in `app/agents/trello/`. Each implements `handle(msg: A2AMessage) -> A2AResponse` and   
       calls `app/tools/*` directly.
   63
   64 ### Session memory
   65
   66 `memory` dict is the only cross-turn state. The CLI keeps it in process; the HTTP API expects the client to    
      echo it back on each request. Key fields: `board_id`, `list_map`, `last_card_id`, `pending_plan` (paused pla   
      n awaiting clarification or destructive confirm), `settings.confirm_mutations`, `settings.dry_run`.
   67
   68 ### Prompt layer
   69
   70 `app/prompt/orchestrator.py` contains `ORCHESTRATOR_CATALOG` (the agent/ask list the LLM plans from) and all   
       prompt templates. Changes to agent capabilities must be reflected here or the orchestrator won't use them.    
   71
   72 ### Slim utilities
   73
   74 `app/utils/trello_summaries.py` — `slim_board`, `slim_boards`, `slim_result_for_answer`. Always use these wh   
      en returning Trello API payloads from agents; raw `/members/me/boards` responses are ~130KB and will blow pa   
      st LLM token limits.
   75
   76 ## Adding a new agent
   77
   78 1. Create `app/agents/trello/myagent.py`, subclass `BaseAgent`, implement `handle()`.
   79 2. Register in `create_default_bus()` in `app/agents/bus.py`.
   80 3. Add the agent name + ask list to `ORCHESTRATOR_CATALOG` in `app/prompt/orchestrator.py`.
   81 4. If the agent makes mutating Trello calls, add `("myagent", "my_ask")` to `MUTATING_STEPS` in `app/governa   
      nce/plan_governance.py`.
   82
   83 ## Non-obvious behaviors
   84
   85 - **`board_hint` empty string = catalog request**: When the orchestrator sends `board.resolve_board` with `b   
      oard_hint=""` and no `board_id`, that signals "list all boards". The catalog flow returns `boards` array (sl   
      immed) with status `"ok"`, not `"clarify_user"`. For new "list all boards" intents, always route to `member.   
      get_my_boards` in the orchestrator catalog — never `board.resolve_board`.
   86 - **Name resolution strategy** (`app/utils/resolution.py`): exact → prefix → substring → Levenshtein ≤2 (sin   
      gle candidate only). If two names are within edit distance 2, it clarifies rather than guessing.
   87 - **`BOARD_SCOPE_ONLY`**: defaults `true` when `TRELLO_BOARD_ID` is set. In that mode, `get_boards` returns    
      only the one board and all plans are locked to it.
   88 - **`DELETE_ITEM=false`** blocks `delete_card` entirely (returns error). Set `true` to enable permanent dele   
      tion.
   89 - **Two-stage orchestrator**: `analyze()` extracts intent/entities, `build_plan()` synthesizes the DAG. The    
      analysis object is passed into `build_plan` so the planner doesn't re-derive intent. If you bypass `analyze(   
      )`, pass `analysis=None` and `build_plan` calls it internally.
   90 - **`pending_plan` in memory** is the serialized Plan DAG. When the next turn arrives with a pending plan, `   
      orchestrator_node` calls `resume_plan()` which patches blocked step inputs based on the user's reply (or aba   
      ndons and rebuilds).
   91 - **Governance**: `confirm_mutations=true` (default) pauses before destructive steps once per plan ID. `dry_   
      run=true` stops at the first mutating step and returns a partial trace.
   92
   93 ## Environment variables
   94
   95 | Variable | Purpose |
   96 |---|---|
   97 | `TRELLO_API_KEY` / `TRELLO_API_TOKEN` | Trello credentials |
   98 | `TRELLO_BOARD_ID` | Default board; enables single-board mode |
   99 | `BOARD_SCOPE_ONLY` | `true` = locked to TRELLO_BOARD_ID |
  100 | `API_KEY` or `OPENAI_API_KEY` | OpenAI key |
  101 | `MODEL` | OpenAI model name (e.g. `gpt-4.1`) |
  102 | `DELETE_ITEM` | `false` (default) blocks card deletion |
  103 | `SESSION_PREFETCH` | `false` (default); prefetches me/boards on first turn |
  104 | `REFERENCE_TIMEZONE` | IANA timezone for relative date resolution |
  105 | `LOG_TRELLO_FULL` | `true` logs full Trello request/response bodies |
  106 | `LOG_LLM_FULL` | `true` logs full LLM prompts and responses |