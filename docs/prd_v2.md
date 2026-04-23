# PRD: Trello Agent

**Version:** 2.0  
**Status:** Draft  
**Last Updated:** 2026-04-21

---

## 1. Overview

### 1.1 Purpose

This document defines the requirements for a Trello Agent — an AI-powered agent capable of reading, navigating, and mutating Trello data through the official Trello REST API (`https://api.trello.com/1`). The agent operates as a conversational or automated orchestrator that traverses the full Trello hierarchy from workspace/member level down to individual checklist items, and can perform updates including moving cards between lists and checking off checklist items.

### 1.2 Goals

- Enable full read access across the Trello hierarchy: Member → Board → List → Card → Checklist → CheckItem.
- Enable write/update actions on Boards, Lists, Cards, Checklists, and CheckItems.
- Support moving a card from one list to another as a first-class action.
- Support checking and unchecking individual checklist items on a card.
- Provide a clear, chainable API interaction model that an agent can follow deterministically.

### 1.3 Non-Goals

- No support for Power-Ups or Plugins in v1.
- No support for Enterprise-level endpoints.
- No webhook management in v1.
- No file attachment uploading in v1.
- No OAuth flow implementation — API Key + Token is the assumed auth method.

---

## 2. User Stories

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-01 | Agent | Get all boards for the authenticated user | I can identify which board to operate on |
| US-02 | Agent | Get all lists on a board | I can understand the board's column structure |
| US-03 | Agent | Get all cards on a board or within a specific list | I can inspect task state |
| US-04 | Agent | Get full details of a single card | I can read its description, due date, labels, and members |
| US-05 | Agent | Get all checklists on a card | I can inspect task progress |
| US-06 | Agent | Get all items within a checklist | I can see which items are complete or incomplete |
| US-07 | Agent | Move a card from one list to another | I can update the workflow stage of a task |
| US-08 | Agent | Check or uncheck a checklist item | I can mark sub-tasks as done or reopen them |
| US-09 | Agent | Update a card's name, description, or due date | I can keep card details current |
| US-10 | Agent | Post a comment on a card | I can leave a trace of agent actions |
| US-11 | Agent | Create a new card in a list | I can add new tasks programmatically |
| US-12 | Agent | Create a new list on a board | I can set up new workflow stages |

---

## 3. API Authentication

All requests to the Trello REST API must include the following query parameters:

```
key=<API_KEY>&token=<API_TOKEN>
```

The `API_KEY` identifies the application (Trello Power-Up). The `API_TOKEN` is a per-user authorization token with read/write scope. Both must be kept secret on the server side and never exposed to the client.

**Base URL:** `https://api.trello.com/1`

**Headers required:**
```
Accept: application/json
Content-Type: application/json   (for POST/PUT requests)
```

---

## 4. Hierarchy & Chaining Model

The agent must traverse the following ID chain to reach any resource. Each level's response provides the ID needed to query the next level.

```
Member (me)
  └── Board (boardId)
        ├── List (listId)
        │     └── Card (cardId)
        │           ├── Checklist (checklistId)
        │           │     └── CheckItem (checkItemId)
        │           ├── Action / Comment (actionId)
        │           └── Label (labelId)
        └── Label (board-level, labelId)
```

The agent must resolve human-readable names (e.g., "the Marketing board", "the To Do list") to IDs by fetching the relevant resource list and matching by `name` field.

---

## 5. Nodes & Capabilities

### 5.1 Member Node

**Purpose:** Entry point. Retrieves the authenticated user and their boards.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/members/me` | Get authenticated user info (id, username, fullName) |
| GET | `/members/me/boards` | List all boards the user belongs to → yields `boardId` |
| GET | `/members/{id}/boards` | Get boards of a specific member by ID |
| GET | `/members/{id}/cards` | Get all cards assigned to this member |

**Key response fields from `/members/me/boards`:**

```json
[
  {
    "id": "<boardId>",
    "name": "My Project Board",
    "closed": false,
    "url": "https://trello.com/b/..."
  }
]
```

**Agent behavior:** On initialization, call `GET /members/me/boards` and store `{ id, name }` for each board. Use this to resolve the user's target board by name.

---

### 5.2 Board Node

**Purpose:** Central hub. All lists, cards, labels, and members are accessed through a `boardId`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/boards/{boardId}` | Get board details (name, desc, prefs, url) |
| PUT | `/boards/{boardId}` | Update board name, description, or background |
| POST | `/boards` | Create a new board |
| GET | `/boards/{boardId}/lists` | Get all lists on board → yields `listId` |
| POST | `/boards/{boardId}/lists` | Create a new list on the board |
| GET | `/boards/{boardId}/cards` | Get all open cards on the board → yields `cardId` |
| GET | `/boards/{boardId}/members` | Get all members of the board |
| GET | `/boards/{boardId}/labels` | Get all labels defined on the board → yields `labelId` |
| GET | `/boards/{boardId}/checklists` | Get all checklists across the board |
| GET | `/boards/{boardId}/actions` | Get activity log for the board |

**Key response fields from `/boards/{boardId}/lists`:**

```json
[
  {
    "id": "<listId>",
    "name": "To Do",
    "closed": false,
    "pos": 1024,
    "idBoard": "<boardId>"
  }
]
```

**Agent behavior:** After resolving `boardId`, call `GET /boards/{boardId}/lists` and store `{ id, name }` for each list. This enables the agent to resolve list names (e.g., "In Progress") to `listId` for card-move operations.

---

### 5.3 List Node

**Purpose:** A column within a board. Contains cards. Needed as both a source and target when moving cards.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/lists/{listId}` | Get list details (name, pos, closed, idBoard) |
| PUT | `/lists/{listId}` | Update list name, position, or closed state |
| GET | `/lists/{listId}/cards` | Get all cards in this list → yields `cardId` |
| POST | `/lists/{listId}/archiveAllCards` | Archive all cards in the list |
| POST | `/lists/{listId}/moveAllCards` | Move all cards to another list or board |
| PUT | `/lists/{listId}/closed` | Archive or unarchive the list |

**Agent behavior:** Use `GET /lists/{listId}/cards` when the agent needs cards scoped to a specific column. Store all list `{ id, name }` pairs from the board-level call to enable name-to-ID resolution for move targets.

---

### 5.4 Card Node

**Purpose:** The primary task unit. Supports the richest set of read and write operations. Moving a card between lists is performed by updating the card's `idList` field.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cards/{cardId}` | Get full card details (name, desc, due, idList, labels, members) |
| POST | `/cards` | Create a new card — requires `idList` in body |
| PUT | `/cards/{cardId}` | Update card fields (see below) |
| DEL | `/cards/{cardId}` | Permanently delete a card |
| GET | `/cards/{cardId}/checklists` | Get all checklists on card → yields `checklistId` |
| GET | `/cards/{cardId}/actions` | Get comments and activity on this card |
| GET | `/cards/{cardId}/attachments` | Get file or URL attachments |
| POST | `/cards/{cardId}/actions/comments` | Post a comment on the card |
| POST | `/cards/{cardId}/checklists` | Add a new checklist to the card |
| POST | `/cards/{cardId}/idMembers` | Assign a member to the card |
| POST | `/cards/{cardId}/idLabels` | Attach a label to the card |
| PUT | `/cards/{cardId}/due` | Set or update the due date |
| PUT | `/cards/{cardId}/dueComplete` | Mark due date as complete/incomplete |

**PUT `/cards/{cardId}` — updatable fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Card title |
| `desc` | string | Card description (Markdown supported) |
| `closed` | boolean | Archive (`true`) or restore (`false`) the card |
| `idList` | string | **Move card to a different list** — set to target `listId` |
| `idBoard` | string | Move card to a different board |
| `pos` | string/number | Position within the list (`top`, `bottom`, or a positive float) |
| `due` | string | ISO 8601 due date or `null` to clear |
| `dueComplete` | boolean | Mark due date as completed |
| `idMembers` | array | Replace the full list of assigned member IDs |
| `idLabels` | array | Replace the full list of assigned label IDs |

**Moving a card between lists — required call:**

```
PUT /cards/{cardId}
Body: { "idList": "<targetListId>" }
```

The agent must have resolved `targetListId` from the board's list map before issuing this call.

---

### 5.5 Checklist Node

**Purpose:** A checklist attached to a card. Contains ordered check items that can be individually marked complete or incomplete.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/checklists/{checklistId}` | Get checklist with name and all items |
| PUT | `/checklists/{checklistId}` | Update checklist name or position |
| DEL | `/checklists/{checklistId}` | Delete the entire checklist |
| GET | `/checklists/{checklistId}/checkItems` | List all check items → yields `checkItemId` |
| POST | `/checklists/{checklistId}/checkItems` | Add a new item to the checklist |
| DEL | `/checklists/{checklistId}/checkItems/{checkItemId}` | Delete a single check item |

**Updating a check item state — required call:**

```
PUT /cards/{cardId}/checkItem/{checkItemId}
Body: { "state": "complete" }   ← or "incomplete"
```

> Note: The check item update route lives under `/cards/`, not `/checklists/`. Both `cardId` and `checkItemId` are required.

**POST `/checklists/{checklistId}/checkItems` — create item body:**

```json
{
  "name": "Write unit tests",
  "pos": "bottom",
  "checked": false
}
```

**Key response fields from `/checklists/{checklistId}/checkItems`:**

```json
[
  {
    "id": "<checkItemId>",
    "name": "Write unit tests",
    "state": "incomplete",
    "pos": 1024,
    "idChecklist": "<checklistId>"
  }
]
```

---

### 5.6 Action Node (Activity / Comments)

**Purpose:** Represents anything that has happened on a card or board — moves, comments, member assignments, etc. Used for reading history and posting comments.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/actions/{actionId}` | Get a specific action by ID |
| PUT | `/actions/{actionId}` | Update a comment (text edit) |
| DEL | `/actions/{actionId}` | Delete a comment |
| GET | `/cards/{cardId}/actions` | All activity and comments on a card |
| GET | `/boards/{boardId}/actions` | All activity on a board (supports `filter` param) |
| POST | `/cards/{cardId}/actions/comments` | Post a new comment on a card |

**POST comment body:**

```json
{
  "text": "Agent moved this card to Done after all checklist items were completed."
}
```

---

### 5.7 Label Node

**Purpose:** Tags defined at the board level and applied to cards for categorization.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/labels/{labelId}` | Get label details (name, color, idBoard) |
| PUT | `/labels/{labelId}` | Update label name or color |
| DEL | `/labels/{labelId}` | Delete a label from the board |
| GET | `/boards/{boardId}/labels` | List all labels on a board |
| POST | `/boards/{boardId}/labels` | Create a new label |
| POST | `/cards/{cardId}/idLabels` | Assign a label to a card |
| DEL | `/cards/{cardId}/idLabels/{labelId}` | Remove a label from a card |

---

## 6. Core Agent Flows

### 6.1 Read Full Board State

Used to build the agent's internal context map before any mutation.

```
1. GET /members/me/boards
   → store [{ id, name }] as boardMap

2. GET /boards/{boardId}/lists
   → store [{ id, name }] as listMap

3. GET /boards/{boardId}/cards
   → store [{ id, name, idList, desc, due, dueComplete, idChecklists }] as cardMap

4. For each card requiring deep inspection:
   GET /cards/{cardId}/checklists
   → store [{ id, name, checkItems: [{ id, name, state }] }]
```

### 6.2 Move a Card to a Different List

```
Precondition: boardId, cardId, and target list name are known.

1. Resolve target listId:
   match target list name against listMap → get targetListId

2. PUT /cards/{cardId}
   Body: { "idList": "<targetListId>" }

3. (Optional) POST /cards/{cardId}/actions/comments
   Body: { "text": "Moved to <listName> by agent." }
```

### 6.3 Check / Uncheck a Checklist Item

```
Precondition: cardId and item name (or checkItemId) are known.

1. GET /cards/{cardId}/checklists
   → get checklistId(s) on the card

2. GET /checklists/{checklistId}/checkItems
   → resolve item name to checkItemId

3. PUT /cards/{cardId}/checkItem/{checkItemId}
   Body: { "state": "complete" }   ← or "incomplete"
```

### 6.4 Create a Card in a Specific List

```
1. Resolve listId from listMap by list name.

2. POST /cards
   Body: {
     "idList": "<listId>",
     "name": "Card title",
     "desc": "Optional description",
     "due": "2026-05-01T00:00:00.000Z"   ← optional
   }
```

### 6.5 Update a Card's Details

```
PUT /cards/{cardId}
Body (any combination of):
{
  "name": "Updated title",
  "desc": "Updated description",
  "due": "2026-05-15T00:00:00.000Z",
  "dueComplete": false
}
```

---

## 7. Error Handling

| HTTP Status | Meaning | Agent behavior |
|-------------|---------|---------------|
| 200 | Success | Parse response and continue |
| 400 | Bad request / missing required field | Log error, abort current action, surface to caller |
| 401 | Invalid API key or token | Halt agent, surface auth error |
| 403 | Insufficient permissions | Log and skip; do not retry |
| 404 | Resource not found | Re-fetch parent resource to verify IDs are still valid |
| 429 | Rate limit exceeded | Wait and retry with exponential backoff (start at 1s) |
| 500 | Trello server error | Retry up to 3 times with backoff; then surface error |

**Rate limits:** Trello enforces 100 requests per 10-second window per token. The agent must track request counts and throttle accordingly.

---

## 8. Data Models

### Board
```typescript
interface Board {
  id: string;
  name: string;
  desc: string;
  closed: boolean;
  url: string;
  idOrganization: string;
}
```

### List
```typescript
interface List {
  id: string;
  name: string;
  closed: boolean;
  pos: number;
  idBoard: string;
}
```

### Card
```typescript
interface Card {
  id: string;
  name: string;
  desc: string;
  closed: boolean;
  idList: string;
  idBoard: string;
  pos: number;
  due: string | null;
  dueComplete: boolean;
  idChecklists: string[];
  idMembers: string[];
  idLabels: string[];
  url: string;
}
```

### Checklist
```typescript
interface Checklist {
  id: string;
  name: string;
  idCard: string;
  idBoard: string;
  pos: number;
  checkItems: CheckItem[];
}
```

### CheckItem
```typescript
interface CheckItem {
  id: string;
  name: string;
  state: 'complete' | 'incomplete';
  pos: number;
  idChecklist: string;
}
```

### Action (Comment)
```typescript
interface Action {
  id: string;
  type: string;            // e.g. "commentCard", "updateCard"
  date: string;            // ISO 8601
  idMemberCreator: string;
  data: {
    text?: string;         // for commentCard
    card?: { id: string; name: string; };
    listBefore?: { id: string; name: string; };  // for card moves
    listAfter?: { id: string; name: string; };
  };
}
```

---

## 9. Implementation Notes

**ID resolution strategy:** The agent should build and cache a local map of `{ name → id }` for boards, lists, and labels at session start. This avoids redundant API calls when the agent needs to resolve human-readable names to IDs mid-flow.

**Checklist item updates use the card route:** The `PUT /cards/{cardId}/checkItem/{checkItemId}` endpoint — not the checklist route — is used for state updates. Both IDs are always required.

**Pagination:** Trello list responses are not paginated by default but support `limit` and `before`/`since` query params on action endpoints. For boards with many actions, use `?limit=50&before={actionId}` to paginate.

**Field filtering:** All GET endpoints support a `fields` query param (e.g., `?fields=name,idList,due`) to reduce response payload. The agent should use field filtering on high-frequency calls to stay within rate limits.

**Idempotency:** PUT and POST calls are not inherently idempotent in Trello. The agent should verify the current state before issuing a mutation (e.g., confirm a card is not already in the target list before moving it).

---

## 10. Out of Scope for v1

- Webhook registration and event-driven triggers
- Attachment file uploads (multipart/form-data)
- Custom Fields read/write
- Power-Up data access
- OAuth 2.0 token flow
- Enterprise organization endpoints
- Board template creation