# PRD: Trello Agent

**Version:** 1.0  
**Status:** Draft  
**Last Updated:** 2026-04-21

## Trello AI Agent — Fully Agentic LangGraph Architecture

---

## 1. Objective

Design and implement a **production-grade, fully agentic Trello AI system** using LangGraph that:

- Accepts natural language via a single FastAPI endpoint
- Interprets user intent using LLM reasoning
- Executes real Trello API actions (read + write)
- Iteratively evaluates and improves responses via structured control loops
- Avoids caching to ensure real-time data accuracy

This system replaces traditional RAG with **tool-based execution over Trello APIs**.

---

## 2. Scope

### In Scope

- Trello API integration (boards, lists, cards)
- LangGraph orchestration
- Multi-step reasoning (plan → act → observe)
- Evaluation + retry + reflection loops
- Batch API usage where applicable

### Out of Scope

- Vector databases (Qdrant, embeddings)
- Caching layers (Redis for retrieval)
- External knowledge augmentation

---

## 3. High-Level Architecture

```
Client (Chat)
   ↓
FastAPI Endpoint
   ↓
LangGraph Agent
   ↓
Trello REST API
```

---

## 4. LangGraph Topology

```
START
  ↓
normalize_intent_planner
  ↓
entity_resolver
  ↓
tool_router
  ↓
tool_executor
  ↓
tool_observer
  ↓
answer_generator
  ↓
evaluation
  ↓
route_after_evaluation
   ├── retry → tool_router
   ├── reflection → reflection_node → END
   └── END
```

---

## 5. State Schema (ChatState)

### Input

- question: str
- history: list

### Planning

- cleaned_query: str
- intent: str
- entities: dict
- reasoning_trace: str

### Execution

- selected_tool: str
- tool_input: dict
- raw_response: dict
- parsed_response: dict

### Output

- answer: str

### Evaluation

- evaluation_result: dict
- evaluation_retry_count: int
- error_message: str

---

## 6. Node Specifications

### 6.1 normalize_intent_planner

**Type:** LLM Node

**Purpose:**

- Normalize input
- Extract structured intent
- Perform deep semantic reasoning

**Output Example:**

```json
{
  "intent": "create_card",
  "entities": {
    "board_name": "Marketing",
    "list_name": "To Do",
    "card_name": "Prepare campaign",
    "description": "Draft content"
  },
  "reasoning": "User wants to create a new task"
}
```

**Notes:**

- This node replaces traditional RAG intent usage
- Must be schema-constrained (JSON mode)

---

### 6.2 entity_resolver

**Type:** Deterministic Node

**Purpose:**

- Resolve names → IDs via Trello API

**Examples:**

- board_name → board_id
- list_name → list_id

**Behavior:**

- Uses batch API calls (e.g., fetch all boards once per turn)
- No caching across sessions

---

### 6.3 tool_router

**Type:** Deterministic Mapping

**Purpose:**
Map intent → Trello API endpoint


| Intent      | Endpoint                     |
| ----------- | ---------------------------- |
| get_boards  | GET /1/members/me/boards     |
| get_lists   | GET /1/boards/{id}/lists     |
| get_cards   | GET /1/lists/{id}/cards      |
| create_card | POST /1/cards                |
| update_card | PUT /1/cards/{id}            |
| move_card   | PUT /1/cards/{id}?idList=... |


---

### 6.4 tool_executor

**Type:** HTTP Node

**Purpose:**
Execute Trello API requests

**Input:**

- endpoint
- method
- params/body

**Output:**

- raw_response
- status_code

**Requirements:**

- Timeout handling
- Retry mechanism (exponential backoff)
- Logging

---

### 6.5 tool_observer

**Type:** Deterministic Transformer

**Purpose:**
Convert raw API response → structured format

**Example Output:**

```json
{
  "cards": [
    {"name": "Task A", "due": "2026-04-21"}
  ]
}
```

---

### 6.6 answer_generator

**Type:** LLM Node

**Purpose:**
Generate human-readable response

**Input:**

- user query
- parsed_response

---

### 6.7 evaluation

**Type:** Hybrid (Deterministic + LLM)

**Purpose:**

- Validate correctness
- Detect failure or ambiguity

**Checks:**

- API success
- Output relevance

---

### 6.8 retry

**Trigger:**

- API failure
- Missing entities

**Behavior:**

- Adjust tool input
- Re-route execution

---

### 6.9 reflection_node

**Type:** LLM Node

**Purpose:**

- Final fallback
- Explain failure gracefully

---

## 7. Trello API Strategy

### Principles

- No caching
- Prefer batch retrieval
- Minimize API calls per turn

### Example Optimization

Instead of:

- Get boards → get lists → get cards sequentially

Use:

- Pre-fetch lists/cards in minimal calls when possible

---

## 8. Error Handling Strategy


| Scenario           | Handling           |
| ------------------ | ------------------ |
| Missing board/list | Ask clarification  |
| API failure        | Retry with backoff |
| Ambiguous intent   | Re-run planner     |
| Persistent failure | Reflection node    |


---

## 9. Evaluation Routing Logic

```
if success:
  END
elif retry_count < threshold:
  retry
else:
  reflection
```

---

## 10. Deployment

### Stack

- FastAPI
- LangGraph
- Trello REST API

### Endpoint

```
POST /chat
```

---

## 11. Observability

- Request logging
- API latency tracking
- Failure rate monitoring

---

## 12. Risks & Trade-offs

### Pros

- Real-time accuracy
- No stale data
- Full action capability

### Cons

- Higher latency
- API dependency
- Complex state management

---

## 13. Future Extensions

- Multi-step workflows (e.g., create board + lists)
- Role-based permissions
- Hybrid RAG integration

---

## 14. References

- ReAct Paper (Yao et al., 2022)
- Trello REST API (Atlassian)
- LangGraph Documentation

