# PRD: Trello Agent — v3.0

**Version:** 3.0
**Status:** Draft
**Last Updated:** 2026-04-22
**Supersedes:** prd_v2.md

---

## Table of Contents

1. [Overview](#1-overview)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [User Stories](#3-user-stories)
4. [Authentication & Security](#4-authentication--security)
5. [API Hierarchy & Chaining Model](#5-api-hierarchy--chaining-model)
6. [Full Capability Map](#6-full-capability-map)
   - 6.1 Member Node
   - 6.2 Board Node
   - 6.3 List Node
   - 6.4 Card Node
   - 6.5 Checklist Node
   - 6.6 CheckItem Node
   - 6.7 Label Node
   - 6.8 Action / Comment Node
   - 6.9 Attachment Node
   - 6.10 Custom Field Node *(v3 new)*
   - 6.11 Webhook Node *(v3 new)*
   - 6.12 Organization / Workspace Node *(v3 new)*
   - 6.13 Search Node *(v3 new)*
   - 6.14 Notification Node *(v3 new)*
7. [Agent Intent Taxonomy](#7-agent-intent-taxonomy)
8. [NLP & Intent Resolution](#8-nlp--intent-resolution)
9. [Core Agent Flows](#9-core-agent-flows)
10. [Context & Memory Model](#10-context--memory-model)
11. [Rate Limiting & Throttling](#11-rate-limiting--throttling)
12. [Error Handling](#12-error-handling)
13. [Data Models](#13-data-models)
14. [Agent Reasoning Protocol](#14-agent-reasoning-protocol)
15. [Testing & Validation Matrix](#15-testing--validation-matrix)
16. [Out of Scope for v3](#16-out-of-scope-for-v3)
17. [Open Questions](#17-open-questions)

---

## 1. Overview

### 1.1 Purpose

This document defines requirements for **Trello Agent v3** — a fully capable, conversational AI agent that reads, navigates, and mutates all addressable Trello resources through the official Trello REST API (`https://api.trello.com/1`).

v3 expands significantly beyond v2 by adding:

- Full Custom Fields read/write
- Webhook registration and event-driven triggers
- Organization/Workspace-level operations
- Cross-board search
- Notification management
- Structured NLP intent taxonomy with 60+ recognized intents
- A formal agent reasoning protocol with plan-before-act behavior
- Multi-step conversational flows with disambiguation
- Idempotency guards and dry-run mode

### 1.2 Design Principles

- **Hierarchy-first**: The agent always resolves human names to IDs by traversing the Trello hierarchy top-down. It never guesses an ID.
- **Minimal surface area**: The agent fetches only the fields it needs using the `fields` query parameter.
- **Confirm before mutate**: All destructive or irreversible mutations (delete card, archive board, clear checklist) require explicit confirmation unless the user has set `confirm_mutations: false`.
- **Transparent reasoning**: The agent exposes its intent classification, the API calls it is about to make, and the result in a structured trace.
- **Graceful degradation**: If a resource is not found, the agent re-fetches the parent and retries once before surfacing an error.
- **Idempotency guards**: Before every mutation the agent checks current state and skips the call if the desired state already exists.

---

## 2. Goals & Non-Goals

### 2.1 Goals

- Full CRUD on all primary Trello resources: Boards, Lists, Cards, Checklists, CheckItems, Labels, Actions, Attachments, Members.
- Read and write Custom Fields on cards and boards.
- Register, list, and delete Webhooks.
- Query and manage Organization/Workspace memberships and boards.
- Full-text search across boards, cards, and members.
- Read and dismiss notifications.
- Natural language understanding across broad question types ("what's overdue", "summarize my week", "who's working on what").
- Conversational multi-turn flows with disambiguation for ambiguous inputs.
- Dry-run mode: show the agent's planned API calls without executing them.
- Rate-limit awareness with per-token request budgeting.

### 2.2 Non-Goals (v3)

- OAuth 2.0 token flow UI (API Key + Token assumed).
- Attachment file upload (multipart/form-data binary transfers).
- Power-Up registration or data storage.
- Enterprise organization admin endpoints.
- Real-time streaming / SSE webhooks from Trello (only outbound webhook registration).
- Board template creation from existing boards.
- Butler / automation rule management.

---

## 3. User Stories

### 3.1 Read / Query

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-01 | Agent | Get authenticated user info and all their boards | I have the entry point for all operations |
| US-02 | Agent | Get all lists on a board | I understand the board's column structure |
| US-03 | Agent | Get all open cards on a board or list | I can inspect task state |
| US-04 | Agent | Get full details of a single card | I can read name, desc, due, labels, members, custom fields |
| US-05 | Agent | Get all checklists and their items on a card | I can inspect sub-task progress |
| US-06 | Agent | Get all labels on a board | I can resolve label names to IDs for assignment |
| US-07 | Agent | Get board members and their roles | I can assign tasks and filter by person |
| US-08 | Agent | Get all custom fields defined on a board | I can read and write structured metadata |
| US-09 | Agent | Get custom field values set on a specific card | I can surface structured data in responses |
| US-10 | Agent | Search across boards, cards, and members | I can find resources by keyword without knowing exact location |
| US-11 | Agent | Get all notifications for the authenticated user | I can surface mentions, assignments, and due reminders |
| US-12 | Agent | Get organization/workspace boards and members | I can operate at the org level |
| US-13 | Agent | Get card activity/comments history | I can summarize what happened on a task |

### 3.2 Write / Mutate

| ID | As a... | I want to... | So that... |
|----|---------|--------------|------------|
| US-14 | Agent | Create a card in a specific list | I can add new tasks programmatically |
| US-15 | Agent | Update a card's name, description, due date, or position | I can keep card details current |
| US-16 | Agent | Move a card to a different list or board | I can update workflow stage |
| US-17 | Agent | Archive or restore a card | I can manage task lifecycle |
| US-18 | Agent | Delete a card permanently | I can remove unwanted tasks (with confirmation) |
| US-19 | Agent | Add or remove a member from a card | I can manage task ownership |
| US-20 | Agent | Add or remove a label from a card | I can categorize tasks |
| US-21 | Agent | Set or clear a card's due date | I can manage deadlines |
| US-22 | Agent | Mark or unmark a card's due date as complete | I can track completion |
| US-23 | Agent | Add a new checklist to a card | I can break tasks into sub-tasks |
| US-24 | Agent | Add, update, or delete a checklist item | I can manage sub-task granularity |
| US-25 | Agent | Check or uncheck a checklist item | I can mark sub-tasks complete |
| US-26 | Agent | Post, edit, or delete a comment on a card | I can leave action traces |
| US-27 | Agent | Create, update, or delete a list on a board | I can manage board columns |
| US-28 | Agent | Archive a list | I can retire old workflow stages |
| US-29 | Agent | Create a new board | I can set up new workspaces |
| US-30 | Agent | Update a board's name, description, or background | I can maintain board metadata |
| US-31 | Agent | Create or update a label on a board | I can manage categorization taxonomy |
| US-32 | Agent | Set a custom field value on a card | I can write structured metadata |
| US-33 | Agent | Register a webhook on a board or card | I can set up event-driven triggers |
| US-34 | Agent | Delete a webhook | I can clean up stale triggers |

---

## 4. Authentication & Security

### 4.1 Method

All API requests use Trello's API Key + Token auth via query parameters:

```
GET https://api.trello.com/1/members/me?key=<API_KEY>&token=<API_TOKEN>
```

### 4.2 Scopes Required

The token must be authorized with the following scopes:

| Scope | Required for |
|-------|-------------|
| `read` | All GET operations |
| `write` | All POST, PUT, DELETE operations |
| `account` | Member profile, org memberships |

Recommended token expiry: `never` for persistent agent use. For short-lived agents use `30days`.

### 4.3 Secret Handling

- API Key and Token must **never** be logged or included in error messages returned to end users.
- Stored in environment variables: `TRELLO_API_KEY`, `TRELLO_API_TOKEN`.
- Rotated via Trello Power-Up admin if compromised.

### 4.4 Headers

```http
Accept: application/json
Content-Type: application/json   (POST/PUT only)
```

### 4.5 Base URL

```
https://api.trello.com/1
```

---

## 5. API Hierarchy & Chaining Model

The agent must traverse this ID chain deterministically. Each level's response provides the ID(s) needed to query the next.

```
Organization (orgId)
  └── Member (me / memberId)
        └── Board (boardId)
              ├── List (listId)
              │     └── Card (cardId)
              │           ├── Checklist (checklistId)
              │           │     └── CheckItem (checkItemId)
              │           ├── Action / Comment (actionId)
              │           ├── Label assignment (labelId)
              │           ├── Member assignment (memberId)
              │           ├── Attachment (attachmentId)
              │           └── CustomFieldItem (customFieldItemId)
              ├── Label (board-level, labelId)
              ├── CustomField (customFieldId)
              ├── Member (boardMemberId)
              └── Webhook (webhookId)
```

### 5.1 Name-to-ID Resolution Strategy

The agent maintains a session-scoped context map:

```
boardMap:        { boardId → boardName }
listMap:         { listId → listName }
cardMap:         { cardId → { name, idList, due, dueComplete } }
memberMap:       { memberId → { fullName, username } }
labelMap:        { labelId → { name, color } }
customFieldMap:  { customFieldId → { name, type, options } }
webhookMap:      { webhookId → { description, callbackURL, idModel } }
```

Resolution order for ambiguous names:
1. Exact case-insensitive match.
2. Prefix match (longest prefix wins).
3. Fuzzy match (Levenshtein distance ≤ 2, only if exactly one candidate).
4. If zero or multiple candidates → ask user to disambiguate.

---

## 6. Full Capability Map

### 6.1 Member Node

**Purpose:** Entry point. Retrieves the authenticated user and their boards.

| Method | Endpoint | Description | Key Params |
|--------|----------|-------------|------------|
| GET | `/members/me` | Authenticated user info | `fields=id,username,fullName` |
| GET | `/members/me/boards` | All boards the user belongs to | `filter=open`, `fields=id,name,closed` |
| GET | `/members/me/cards` | All cards assigned to authenticated user | `fields=id,name,idList,idBoard,due,dueComplete` |
| GET | `/members/me/notifications` | All notifications | `filter=all`, `limit=50` |
| GET | `/members/{id}` | Get member by ID or username | `fields=id,username,fullName,avatarUrl` |
| GET | `/members/{id}/boards` | Boards a specific member belongs to | `filter=open` |
| GET | `/members/{id}/cards` | Cards assigned to a specific member | |
| PUT | `/members/me` | Update display name or bio | `body: { fullName, bio }` |

**Init behavior:** On session start call `GET /members/me/boards?filter=open&fields=id,name` and cache `boardMap`.

---

### 6.2 Board Node

**Purpose:** Central hub. All lists, cards, labels, members, custom fields, and webhooks belong to a board.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/boards/{boardId}` | Board details | `fields=id,name,desc,closed,url,idOrganization` |
| POST | `/boards` | Create board | `body: { name, desc, defaultLists, idOrganization }` |
| PUT | `/boards/{boardId}` | Update board | `body: { name, desc, closed, prefs/background }` |
| DEL | `/boards/{boardId}` | Delete board *(destructive — requires confirm)* | |
| GET | `/boards/{boardId}/lists` | All lists | `filter=open`, `fields=id,name,pos,closed` |
| POST | `/boards/{boardId}/lists` | Create list | `body: { name, pos }` |
| GET | `/boards/{boardId}/cards` | All open cards | `fields=id,name,idList,due,dueComplete,idMembers,idLabels,idChecklists,desc` |
| GET | `/boards/{boardId}/members` | All board members | `fields=id,username,fullName` |
| PUT | `/boards/{boardId}/members/{memberId}` | Add member to board | `body: { type: "normal"\|"admin"\|"observer" }` |
| DEL | `/boards/{boardId}/members/{memberId}` | Remove member from board | |
| GET | `/boards/{boardId}/labels` | All board labels | `fields=id,name,color` |
| POST | `/boards/{boardId}/labels` | Create label | `body: { name, color }` |
| GET | `/boards/{boardId}/customFields` | All custom field definitions | |
| POST | `/boards/{boardId}/customField` | Create custom field | `body: { name, type, pos, display_cardFront }` |
| GET | `/boards/{boardId}/checklists` | All checklists across board | |
| GET | `/boards/{boardId}/actions` | Board activity log | `filter=commentCard,updateCard,createCard`, `limit=50` |
| GET | `/boards/{boardId}/memberships` | Board memberships with roles | |

---

### 6.3 List Node

**Purpose:** A column within a board. Contains cards. Used as source and target for card moves.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/lists/{listId}` | List details | `fields=id,name,pos,closed,idBoard` |
| PUT | `/lists/{listId}` | Update name, position, or closed | `body: { name, pos, closed }` |
| PUT | `/lists/{listId}/closed` | Archive or restore list | `body: { value: true\|false }` |
| PUT | `/lists/{listId}/pos` | Reposition list | `body: { value: "top"\|"bottom"\|<float> }` |
| GET | `/lists/{listId}/cards` | All cards in list | `fields=id,name,due,dueComplete,idMembers,idLabels` |
| POST | `/lists/{listId}/archiveAllCards` | Archive all cards in list | |
| POST | `/lists/{listId}/moveAllCards` | Move all cards to another list | `body: { idBoard, idList }` |

---

### 6.4 Card Node

**Purpose:** Primary task unit. Supports the richest set of read and write operations.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/cards/{cardId}` | Full card details | `fields=id,name,desc,closed,idList,idBoard,pos,due,dueComplete,idChecklists,idMembers,idLabels,url` |
| POST | `/cards` | Create card | `body: { idList, name, desc, due, pos, idMembers[], idLabels[] }` |
| PUT | `/cards/{cardId}` | Update card (see fields table below) | |
| DEL | `/cards/{cardId}` | Permanently delete card *(confirm required)* | |
| PUT | `/cards/{cardId}/closed` | Archive (`true`) or restore (`false`) | `body: { value: bool }` |
| PUT | `/cards/{cardId}/idList` | Move card to a list | `body: { value: listId }` |
| PUT | `/cards/{cardId}/pos` | Reorder within list | `body: { value: "top"\|"bottom"\|<float> }` |
| PUT | `/cards/{cardId}/due` | Set or clear due date | `body: { value: ISO8601 \| null }` |
| PUT | `/cards/{cardId}/dueComplete` | Mark due complete/incomplete | `body: { value: bool }` |
| PUT | `/cards/{cardId}/name` | Rename card | `body: { value: string }` |
| PUT | `/cards/{cardId}/desc` | Update description | `body: { value: string }` |
| POST | `/cards/{cardId}/idMembers` | Assign member | `body: { value: memberId }` |
| DEL | `/cards/{cardId}/idMembers/{memberId}` | Remove member from card | |
| POST | `/cards/{cardId}/idLabels` | Add label | `body: { value: labelId }` |
| DEL | `/cards/{cardId}/idLabels/{labelId}` | Remove label from card | |
| GET | `/cards/{cardId}/checklists` | All checklists on card | |
| POST | `/cards/{cardId}/checklists` | Add checklist | `body: { name, pos, idChecklistSource? }` |
| GET | `/cards/{cardId}/actions` | Card activity and comments | `filter=commentCard,updateCard`, `limit=50` |
| POST | `/cards/{cardId}/actions/comments` | Post comment | `body: { text }` |
| GET | `/cards/{cardId}/attachments` | All attachments | |
| POST | `/cards/{cardId}/attachments` | Add URL attachment | `body: { url, name, mimeType }` |
| DEL | `/cards/{cardId}/attachments/{attachmentId}` | Remove attachment | |
| GET | `/cards/{cardId}/customFieldItems` | All custom field values on card | |

**`PUT /cards/{cardId}` — full updatable field reference:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Card title |
| `desc` | string | Description (Markdown supported) |
| `closed` | boolean | Archive (`true`) or restore (`false`) |
| `idList` | string | Move to target list |
| `idBoard` | string | Move to target board |
| `pos` | string/float | `"top"`, `"bottom"`, or a positive float |
| `due` | string/null | ISO 8601 due date, or `null` to clear |
| `dueComplete` | boolean | Mark due date complete |
| `start` | string/null | ISO 8601 start date |
| `idMembers` | string[] | Replace full member list |
| `idLabels` | string[] | Replace full label list |
| `address` | string | Physical location |
| `locationName` | string | Display name for location |
| `coordinates` | string | `"lat,long"` |

---

### 6.5 Checklist Node

**Purpose:** A checklist attached to a card.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/checklists/{checklistId}` | Checklist with name and all items | |
| PUT | `/checklists/{checklistId}` | Update name or position | `body: { name, pos }` |
| PUT | `/checklists/{checklistId}/name` | Rename checklist | `body: { value: string }` |
| DEL | `/checklists/{checklistId}` | Delete entire checklist *(confirm required)* | |
| GET | `/checklists/{checklistId}/checkItems` | All check items | `fields=id,name,state,pos` |
| POST | `/checklists/{checklistId}/checkItems` | Add check item | `body: { name, pos, checked }` |

---

### 6.6 CheckItem Node

**Purpose:** Individual item within a checklist. State is toggled via the card route.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/checklists/{checklistId}/checkItems/{checkItemId}` | Get single check item | |
| PUT | `/cards/{cardId}/checkItem/{checkItemId}` | Update state, name, or position | `body: { state: "complete"\|"incomplete", name?, pos? }` |
| DEL | `/checklists/{checklistId}/checkItems/{checkItemId}` | Delete check item | |

> **Critical:** State updates use the **card route** (`/cards/{cardId}/checkItem/...`), not the checklist route. Both `cardId` and `checkItemId` are always required.

---

### 6.7 Label Node

**Purpose:** Tags defined at the board level and applied to cards.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/labels/{labelId}` | Label details | `fields=id,name,color,idBoard` |
| PUT | `/labels/{labelId}` | Update name or color | `body: { name, color }` |
| DEL | `/labels/{labelId}` | Delete label from board *(confirm required)* | |
| GET | `/boards/{boardId}/labels` | All board labels | |
| POST | `/boards/{boardId}/labels` | Create label | `body: { name, color }` |
| POST | `/cards/{cardId}/idLabels` | Assign label to card | `body: { value: labelId }` |
| DEL | `/cards/{cardId}/idLabels/{labelId}` | Remove label from card | |

**Supported colors:** `yellow`, `purple`, `blue`, `red`, `green`, `orange`, `black`, `sky`, `pink`, `lime`, or `null` (colorless).

---

### 6.8 Action / Comment Node

**Purpose:** Represents events (moves, comments, assignments) on a card or board.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/actions/{actionId}` | Get action by ID | |
| PUT | `/actions/{actionId}` | Edit comment text | `body: { text }` |
| DEL | `/actions/{actionId}` | Delete comment | |
| GET | `/cards/{cardId}/actions` | Card activity | `filter=commentCard,updateCard,addMemberToCard`, `limit=50` |
| GET | `/boards/{boardId}/actions` | Board activity | `filter=...`, `limit=50`, `before={actionId}` |
| POST | `/cards/{cardId}/actions/comments` | Post comment | `body: { text }` |

**Action filter values:** `commentCard`, `updateCard`, `createCard`, `deleteCard`, `addMemberToCard`, `removeMemberFromCard`, `addLabelToCard`, `removeLabelFromCard`, `updateCheckItemStateOnCard`, `moveCardToBoard`, `copyCard`.

---

### 6.9 Attachment Node

**Purpose:** URL or file references linked to a card.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/cards/{cardId}/attachments` | All attachments | `fields=id,name,url,mimeType,date` |
| GET | `/cards/{cardId}/attachments/{attachmentId}` | Single attachment | |
| POST | `/cards/{cardId}/attachments` | Add URL attachment | `body: { url, name, mimeType }` |
| DEL | `/cards/{cardId}/attachments/{attachmentId}` | Remove attachment | |

> File upload (binary multipart) is out of scope for v3. URL-based attachments are fully supported.

---

### 6.10 Custom Field Node *(v3 new)*

**Purpose:** Structured metadata fields defined at the board level and set per-card.

#### 6.10.1 Board-Level Definition

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/boards/{boardId}/customFields` | All custom field definitions | |
| POST | `/boards/{boardId}/customField` | Create custom field | `body: { name, type, pos, display_cardFront }` |
| PUT | `/customFields/{customFieldId}` | Update name, pos, or display | `body: { name, pos, display }` |
| DEL | `/customFields/{customFieldId}` | Delete custom field | |
| GET | `/customFields/{customFieldId}/options` | Dropdown options | |
| POST | `/customFields/{customFieldId}/options` | Add dropdown option | `body: { value: { text } }` |
| DEL | `/customFields/{customFieldId}/options/{optionId}` | Remove dropdown option | |

**Custom field types:** `text`, `number`, `date`, `checkbox`, `list` (dropdown).

#### 6.10.2 Card-Level Values

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/cards/{cardId}/customFieldItems` | All custom field values on card | |
| PUT | `/card/{cardId}/customField/{customFieldId}/item` | Set value on card | `body: { value: { text?\|number?\|date?\|checked? }, idValue? }` |

**Set by type:**

```json
// text
{ "value": { "text": "In review" } }

// number
{ "value": { "number": "42" } }

// date
{ "value": { "date": "2026-05-01T00:00:00.000Z" } }

// checkbox
{ "value": { "checked": "true" } }

// list (dropdown) — use idValue, not value
{ "idValue": "<optionId>" }

// clear a value
{ "value": "" }
```

---

### 6.11 Webhook Node *(v3 new)*

**Purpose:** Register outbound callbacks on Trello models so external systems receive events.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/tokens/{token}/webhooks` | All webhooks for this token | |
| POST | `/webhooks` | Register webhook | `body: { description, callbackURL, idModel, active }` |
| GET | `/webhooks/{webhookId}` | Get webhook details | |
| PUT | `/webhooks/{webhookId}` | Update webhook | `body: { description, callbackURL, idModel, active }` |
| DEL | `/webhooks/{webhookId}` | Delete webhook | |

**`idModel`** can be a boardId, cardId, listId, memberId, or orgId.

**Webhook payload structure (outbound to `callbackURL`):**

```json
{
  "action": {
    "type": "updateCard",
    "date": "2026-04-22T10:00:00.000Z",
    "data": {
      "card": { "id": "...", "name": "..." },
      "listBefore": { "id": "...", "name": "..." },
      "listAfter":  { "id": "...", "name": "..." }
    },
    "memberCreator": { "id": "...", "username": "..." }
  },
  "model": { "id": "<boardId>", "name": "..." }
}
```

**Agent behavior:** The agent can register webhooks on behalf of the user for board-level and card-level events. It stores all registered webhooks in `webhookMap` for lifecycle management.

---

### 6.12 Organization / Workspace Node *(v3 new)*

**Purpose:** Workspace-level operations — listing org boards, managing memberships.

| Method | Endpoint | Description | Key Params / Body |
|--------|----------|-------------|-------------------|
| GET | `/organizations/{orgId}` | Org details | `fields=id,name,displayName,url` |
| GET | `/organizations/{orgId}/boards` | All boards in org | `filter=open`, `fields=id,name` |
| GET | `/organizations/{orgId}/members` | All org members | `fields=id,username,fullName` |
| GET | `/organizations/{orgId}/memberships` | Memberships with roles | |
| PUT | `/organizations/{orgId}/members/{memberId}` | Add/update member role | `body: { type: "normal"\|"admin" }` |
| DEL | `/organizations/{orgId}/members/{memberId}` | Remove member from org | |
| GET | `/members/me/organizations` | All orgs the user belongs to | |

---

### 6.13 Search Node *(v3 new)*

**Purpose:** Full-text search across all accessible Trello resources.

| Method | Endpoint | Description | Key Params |
|--------|----------|-------------|------------|
| GET | `/search` | Search boards, cards, members, orgs | `query`, `modelTypes`, `board_fields`, `card_fields`, `boards_limit`, `cards_limit` |
| GET | `/search/members` | Search members by name/username | `query`, `limit` |

**Key query params for `/search`:**

| Param | Type | Description |
|-------|------|-------------|
| `query` | string | Free-text search query |
| `modelTypes` | string | Comma-separated: `cards`, `boards`, `organizations`, `members`, `actions` |
| `card_fields` | string | Fields to include per card result |
| `cards_limit` | int | Max card results (default 10, max 1000) |
| `cards_page` | int | Pagination offset |
| `board_fields` | string | Fields to include per board result |
| `boards_limit` | int | Max board results |
| `partial` | boolean | Enable prefix/partial matching |

**Example — find cards mentioning "payment":**

```
GET /search?query=payment&modelTypes=cards&card_fields=id,name,idList,idBoard&cards_limit=20
```

**Agent behavior:** The agent uses `/search` when the user's query lacks a specific board/list scope, or when they ask for cross-board results like "find all cards about onboarding".

---

### 6.14 Notification Node *(v3 new)*

**Purpose:** Read and dismiss notifications for the authenticated user.

| Method | Endpoint | Description | Key Params |
|--------|----------|-------------|------------|
| GET | `/members/me/notifications` | All notifications | `filter=all`, `read_filter=unread`, `limit=50`, `page=0` |
| GET | `/notifications/{notificationId}` | Single notification | |
| PUT | `/notifications/{notificationId}` | Mark read/unread | `body: { unread: false }` |
| PUT | `/notifications/all/read` | Mark all as read | |

**Notification types:** `addedToCard`, `cardDueSoon`, `changeCard`, `commentCard`, `createdCard`, `declinedInvitationToBoard`, `invitedToBoard`, `mentionedOnCard`, `removedFromBoard`, `updateCheckItemStateOnCard`.

---

## 7. Agent Intent Taxonomy

The agent classifies every user message into one of the following intents before acting. Intents are grouped by resource and operation type.

### 7.1 Query Intents

| Intent ID | Trigger Examples | Primary API Call |
|-----------|-----------------|-----------------|
| `QUERY_MY_TASKS` | "what are my tasks", "show my cards", "what am I working on" | `GET /members/me/cards` |
| `QUERY_DUE_THIS_WEEK` | "due this week", "upcoming deadlines", "what's due soon" | `GET /boards/{id}/cards` + client-side filter |
| `QUERY_OVERDUE` | "overdue cards", "what's late", "missed deadlines" | `GET /boards/{id}/cards` + client-side filter |
| `QUERY_BOARD_SUMMARY` | "summarize my board", "board overview", "what's on the board" | `GET /boards/{id}/cards` + `GET /boards/{id}/lists` |
| `QUERY_LIST_CARDS` | "cards in backlog", "what's in To Do", "show In Progress column" | `GET /lists/{id}/cards` |
| `QUERY_CARD_DETAIL` | "tell me about [card]", "details on [card]", "what's the status of [card]" | `GET /cards/{id}` |
| `QUERY_CARD_CHECKLIST` | "checklist on [card]", "what sub-tasks are on [card]", "show checklist" | `GET /cards/{id}/checklists` |
| `QUERY_CARD_COMMENTS` | "comments on [card]", "what was said about [card]" | `GET /cards/{id}/actions?filter=commentCard` |
| `QUERY_CARD_ACTIVITY` | "history of [card]", "what happened on [card]" | `GET /cards/{id}/actions` |
| `QUERY_BOARD_MEMBERS` | "who's on this board", "show team members" | `GET /boards/{id}/members` |
| `QUERY_MEMBER_CARDS` | "what is [person] working on", "[person]'s tasks" | `GET /members/{id}/cards` |
| `QUERY_LABELS` | "what labels exist", "show all labels" | `GET /boards/{id}/labels` |
| `QUERY_CUSTOM_FIELDS` | "what custom fields are on this board", "show custom field values for [card]" | `GET /boards/{id}/customFields` |
| `QUERY_NOTIFICATIONS` | "show my notifications", "any mentions", "what did I miss" | `GET /members/me/notifications` |
| `QUERY_SEARCH` | "find cards about [topic]", "search for [keyword]" | `GET /search` |
| `QUERY_BOARDS` | "show all my boards", "what boards do I have" | `GET /members/me/boards` |
| `QUERY_ACTIVITY` | "recent activity", "what happened on the board today" | `GET /boards/{id}/actions` |
| `QUERY_ATTACHMENTS` | "attachments on [card]", "links on [card]" | `GET /cards/{id}/attachments` |
| `QUERY_WEBHOOKS` | "what webhooks are registered", "show my webhooks" | `GET /tokens/{token}/webhooks` |

### 7.2 Mutation Intents

| Intent ID | Trigger Examples | Primary API Call |
|-----------|-----------------|-----------------|
| `CARD_CREATE` | "create a card", "add task [name] to [list]", "new card called [name]" | `POST /cards` |
| `CARD_MOVE` | "move [card] to [list]", "transfer [card] to Done", "put [card] in [list]" | `PUT /cards/{id}` (`idList`) |
| `CARD_RENAME` | "rename [card] to [name]", "change title of [card]" | `PUT /cards/{id}` (`name`) |
| `CARD_UPDATE_DESC` | "update description of [card]", "set desc on [card] to [text]" | `PUT /cards/{id}` (`desc`) |
| `CARD_DUE_SET` | "set due date on [card] to [date]", "due [date] for [card]" | `PUT /cards/{id}/due` |
| `CARD_DUE_CLEAR` | "remove due date from [card]", "clear deadline on [card]" | `PUT /cards/{id}/due` (`null`) |
| `CARD_MARK_DONE` | "mark [card] as done", "complete [card]", "finish [card]" | `PUT /cards/{id}/dueComplete` |
| `CARD_MARK_UNDONE` | "reopen [card]", "mark [card] incomplete", "uncheck [card]" | `PUT /cards/{id}/dueComplete` |
| `CARD_ARCHIVE` | "archive [card]", "hide [card]" | `PUT /cards/{id}/closed` (`true`) |
| `CARD_RESTORE` | "restore [card]", "unarchive [card]" | `PUT /cards/{id}/closed` (`false`) |
| `CARD_DELETE` | "delete [card]", "remove [card] permanently" | `DEL /cards/{id}` *(confirm required)* |
| `CARD_ASSIGN_MEMBER` | "assign [person] to [card]", "add [person] to [card]" | `POST /cards/{id}/idMembers` |
| `CARD_REMOVE_MEMBER` | "remove [person] from [card]", "unassign [person]" | `DEL /cards/{id}/idMembers/{memberId}` |
| `CARD_ADD_LABEL` | "add [label] label to [card]", "tag [card] as [label]" | `POST /cards/{id}/idLabels` |
| `CARD_REMOVE_LABEL` | "remove [label] from [card]" | `DEL /cards/{id}/idLabels/{labelId}` |
| `CARD_ADD_COMMENT` | "comment [text] on [card]", "post note on [card]" | `POST /cards/{id}/actions/comments` |
| `CARD_EDIT_COMMENT` | "edit my comment on [card]" | `PUT /actions/{actionId}` |
| `CARD_DELETE_COMMENT` | "delete comment on [card]" | `DEL /actions/{actionId}` |
| `CARD_ADD_ATTACHMENT` | "add link [url] to [card]" | `POST /cards/{id}/attachments` |
| `CARD_REMOVE_ATTACHMENT` | "remove attachment from [card]" | `DEL /cards/{id}/attachments/{id}` |
| `CHECKLIST_CREATE` | "add checklist [name] to [card]" | `POST /cards/{id}/checklists` |
| `CHECKLIST_DELETE` | "delete checklist [name] from [card]" | `DEL /checklists/{id}` *(confirm required)* |
| `CHECKITEM_ADD` | "add item [name] to checklist on [card]" | `POST /checklists/{id}/checkItems` |
| `CHECKITEM_CHECK` | "check off [item] on [card]", "mark [item] done" | `PUT /cards/{id}/checkItem/{id}` (`complete`) |
| `CHECKITEM_UNCHECK` | "uncheck [item]", "reopen [item] on [card]" | `PUT /cards/{id}/checkItem/{id}` (`incomplete`) |
| `CHECKITEM_RENAME` | "rename checklist item [old] to [new]" | `PUT /cards/{id}/checkItem/{id}` (`name`) |
| `CHECKITEM_DELETE` | "delete item [name] from checklist" | `DEL /checklists/{id}/checkItems/{id}` |
| `LIST_CREATE` | "create list [name]", "add column [name]" | `POST /boards/{id}/lists` |
| `LIST_RENAME` | "rename list [old] to [new]", "rename column" | `PUT /lists/{id}` |
| `LIST_ARCHIVE` | "archive [list] column", "hide [list]" | `PUT /lists/{id}/closed` |
| `LIST_MOVE_ALL_CARDS` | "move all cards from [list] to [list]" | `POST /lists/{id}/moveAllCards` |
| `BOARD_CREATE` | "create a new board called [name]" | `POST /boards` |
| `BOARD_RENAME` | "rename board to [name]" | `PUT /boards/{id}` |
| `BOARD_ARCHIVE` | "archive this board" | `PUT /boards/{id}/closed` |
| `LABEL_CREATE` | "create label [name] in [color]" | `POST /boards/{id}/labels` |
| `LABEL_UPDATE` | "rename label [name] to [name]", "change label color" | `PUT /labels/{id}` |
| `LABEL_DELETE` | "delete label [name]" | `DEL /labels/{id}` *(confirm required)* |
| `CUSTOM_FIELD_SET` | "set [field] on [card] to [value]" | `PUT /card/{id}/customField/{id}/item` |
| `CUSTOM_FIELD_CLEAR` | "clear [field] on [card]" | `PUT /card/{id}/customField/{id}/item` (`""`) |
| `WEBHOOK_CREATE` | "register webhook [url] on this board" | `POST /webhooks` |
| `WEBHOOK_DELETE` | "delete webhook [id/url]" | `DEL /webhooks/{id}` |
| `NOTIFICATION_READ` | "mark notifications as read", "dismiss all notifications" | `PUT /notifications/all/read` |

---

## 8. NLP & Intent Resolution

### 8.1 Pipeline

```
User Input
    │
    ▼
1. Normalize   → lowercase, strip punctuation, expand contractions
    │
    ▼
2. Slot Fill   → extract entity slots: card name, list name, member name,
                 label name, date, checklist name, item name, URL, value
    │
    ▼
3. Intent Match → keyword + pattern matching against Intent Taxonomy (Section 7)
    │              If confidence < 0.7 → route to LLM classifier
    ▼
4. ID Resolve  → map slot values to IDs using context maps
    │              If ambiguous → disambiguation prompt
    ▼
5. Confirm     → if mutation is destructive → confirmation prompt
    │              if dry_run mode → print plan, stop
    ▼
6. Execute     → issue API calls in sequence
    │
    ▼
7. Respond     → format result as natural language + structured card list
```

### 8.2 Slot Extraction Examples

| User Input | Intent | Extracted Slots |
|-----------|--------|-----------------|
| "move the payment bug card to done" | `CARD_MOVE` | card="payment bug", targetList="Done" |
| "assign alice to fix login issue" | `CARD_ASSIGN_MEMBER` | member="alice", card="fix login issue" |
| "what are my tasks due this week" | `QUERY_DUE_THIS_WEEK` | (self-contained) |
| "set the priority field on redesign to high" | `CUSTOM_FIELD_SET` | field="priority", card="redesign", value="high" |
| "add item write tests to the QA checklist on deploy pipeline" | `CHECKITEM_ADD` | item="write tests", checklist="QA checklist", card="deploy pipeline" |
| "mark wireframes complete on the onboarding card" | `CHECKITEM_CHECK` | item="wireframes", card="onboarding" |
| "show me what bob is working on" | `QUERY_MEMBER_CARDS` | member="bob" |

### 8.3 Disambiguation Prompt Templates

**Multiple cards match:**
> I found multiple cards matching "[name]":
> 1. **[Card A]** — in [List], due [Date]
> 2. **[Card B]** — in [List], due [Date]
> Which one did you mean? Reply with 1 or 2, or give me more context.

**List not found:**
> I couldn't find a list called "[name]" on **[Board]**.
> Available lists: **Backlog**, **In Progress**, **Review**, **Done**.
> Which one did you mean?

**Member not found:**
> I couldn't find a member named "[name]" on this board.
> Board members are: **Alice Chen**, **Bob Torres**.
> Did you mean one of them?

### 8.4 Date Parsing

The agent resolves relative dates to ISO 8601 using the current session timestamp:

| User Input | Resolved To |
|-----------|-------------|
| "today" | `<today>T23:59:59.000Z` |
| "tomorrow" | `<today+1>T23:59:59.000Z` |
| "next Friday" | ISO date of next Friday |
| "end of month" | Last day of current month |
| "May 1st" | `2026-05-01T23:59:59.000Z` |
| "in 3 days" | `<today+3>T23:59:59.000Z` |

---

## 9. Core Agent Flows

### 9.1 Session Initialization

```
1. GET /members/me?fields=id,username,fullName
   → store member info

2. GET /members/me/boards?filter=open&fields=id,name
   → store boardMap

3. (if user specifies or defaults to one board):
   GET /boards/{boardId}/lists?filter=open&fields=id,name,pos
   → store listMap

   GET /boards/{boardId}/labels?fields=id,name,color
   → store labelMap

   GET /boards/{boardId}/members?fields=id,username,fullName
   → store memberMap

   GET /boards/{boardId}/customFields
   → store customFieldMap
```

### 9.2 Read Full Board State

```
GET /boards/{boardId}/cards?fields=id,name,idList,due,dueComplete,idMembers,idLabels,idChecklists,desc
→ store cardMap

For each card requiring deep inspection (checklist query):
  GET /cards/{cardId}/checklists
  → store checklistMap per card
```

### 9.3 Move Card Between Lists

```
Preconditions: boardId known, card name resolved to cardId, target list name resolved to targetListId.

1. Idempotency check: if card.idList === targetListId → skip, respond "already there"

2. PUT /cards/{cardId}
   Body: { "idList": "<targetListId>" }

3. POST /cards/{cardId}/actions/comments
   Body: { "text": "Moved to <targetListName> by Trello Agent." }

4. Update local cardMap[cardId].idList = targetListId
```

### 9.4 Check / Uncheck Checklist Item

```
Preconditions: cardId known, item name known.

1. GET /cards/{cardId}/checklists
   → find checklistId(s)

2. GET /checklists/{checklistId}/checkItems
   → resolve item name to checkItemId

3. Idempotency check: if item.state already equals target state → skip

4. PUT /cards/{cardId}/checkItem/{checkItemId}
   Body: { "state": "complete" | "incomplete" }
```

### 9.5 Create Card with Full Metadata

```
1. Resolve listId from listMap.
2. Resolve memberIds[] from memberMap (if any).
3. Resolve labelIds[] from labelMap (if any).
4. Parse due date (if any).

5. POST /cards
   Body: {
     "idList":    "<listId>",
     "name":      "<title>",
     "desc":      "<description>",
     "due":       "<ISO8601 | null>",
     "idMembers": ["<memberId>", ...],
     "idLabels":  ["<labelId>", ...]
   }

6. (optional) For each checklist specified:
   POST /cards/{cardId}/checklists
   Body: { "name": "<checklistName>" }
   
   For each item in checklist:
   POST /checklists/{checklistId}/checkItems
   Body: { "name": "<itemName>", "pos": "bottom" }
```

### 9.6 Set Custom Field Value on Card

```
1. Resolve customFieldId from customFieldMap by field name.
2. Determine field type from customFieldMap[id].type.

3a. For text/number/date/checkbox:
    PUT /card/{cardId}/customField/{customFieldId}/item
    Body: { "value": { "<type>": "<value>" } }

3b. For list (dropdown):
    Resolve optionId from customFieldMap[id].options by option text.
    PUT /card/{cardId}/customField/{customFieldId}/item
    Body: { "idValue": "<optionId>" }

3c. To clear:
    PUT /card/{cardId}/customField/{customFieldId}/item
    Body: { "value": "" }
```

### 9.7 Cross-Board Search

```
1. GET /search?query=<keyword>&modelTypes=cards&card_fields=id,name,idList,idBoard&cards_limit=20&partial=true

2. Group results by board name.

3. For each result, resolve listName from idBoard's listMap
   (re-fetch lists for boards not in current listMap).

4. Return formatted card list grouped by board.
```

### 9.8 Summarize My Week (Compound Query)

```
1. GET /members/me/cards?fields=id,name,idBoard,idList,due,dueComplete
   → all cards assigned to me

2. Client-side filter into buckets:
   - overdue:    due < now && !dueComplete
   - due_today:  due is today && !dueComplete
   - due_week:   due within 7 days && !dueComplete
   - done:       dueComplete === true

3. For each bucket, resolve board + list names.

4. Compose summary response:
   "This week you have:
    - X cards overdue
    - Y cards due today
    - Z cards due in the next 7 days
    - W cards completed"
```

### 9.9 Webhook Registration

```
1. Confirm target model (board, card, or list) with user.
2. Confirm callbackURL with user.

3. POST /webhooks
   Body: {
     "description": "<user-provided label>",
     "callbackURL": "<url>",
     "idModel":     "<boardId | cardId | listId>",
     "active":      true
   }

4. Store result in webhookMap.
5. Respond with webhook ID and confirmation.
```

---

## 10. Context & Memory Model

### 10.1 Session Context

The agent maintains a single `AgentContext` object per conversation session:

```typescript
interface AgentContext {
  member:          { id: string; fullName: string; username: string };
  boardMap:        Record<string, string>;           // boardId → name
  currentBoardId:  string;
  listMap:         Record<string, string>;           // listId → name
  cardMap:         Record<string, CardSummary>;      // cardId → summary
  memberMap:       Record<string, MemberSummary>;    // memberId → summary
  labelMap:        Record<string, LabelSummary>;     // labelId → summary
  customFieldMap:  Record<string, CustomFieldDef>;   // cfId → definition
  webhookMap:      Record<string, WebhookSummary>;   // webhookId → summary
  lastMentionedCard:  string | null;                 // cardId
  lastMentionedList:  string | null;                 // listId
  conversationTurns:  ConversationTurn[];
  settings: {
    confirm_mutations:  boolean;  // default: true
    dry_run:            boolean;  // default: false
    default_board:      string | null;
    timezone:           string;   // e.g. "Asia/Jakarta"
  };
}
```

### 10.2 Pronoun / Anaphora Resolution

When the user refers to "it", "that card", "this task", "the same card", the agent resolves to `context.lastMentionedCard`. If ambiguous across multiple mentioned entities, the agent asks for clarification.

### 10.3 Context Staleness

Context maps are refreshed:
- Board context (lists, labels, members): on board switch or when a 404 is received.
- Card map: after any card mutation.
- On explicit user request: "refresh board" or "reload context".

---

## 11. Rate Limiting & Throttling

### 11.1 Trello Rate Limits

| Limit | Value |
|-------|-------|
| Requests per 10 seconds per token | 100 |
| Requests per 10 seconds per API key | 300 |

### 11.2 Agent Throttling Strategy

- The agent tracks a rolling count of requests in a 10-second window.
- If approaching the limit (≥ 90 in 10s), the agent inserts a `1s` sleep before the next request.
- On HTTP 429, the agent waits `Retry-After` seconds (default 10s if header absent) before retrying.
- Compound queries that would require > 50 API calls must warn the user and offer to paginate results interactively.

### 11.3 Field Filtering

All GET calls must use the `fields` query parameter to request only needed fields. Example:

```
GET /boards/{boardId}/cards?fields=id,name,idList,due,dueComplete,idMembers,idLabels
```

This reduces response payload by ~70% versus fetching all fields.

---

## 12. Error Handling

### 12.1 HTTP Status Handling

| Status | Meaning | Agent Behavior |
|--------|---------|---------------|
| 200 | Success | Parse and continue |
| 400 | Bad request / missing field | Log error, surface specific missing field to user, do not retry |
| 401 | Invalid API key or token | Halt agent, surface auth error, prompt for new credentials |
| 403 | Insufficient permissions | Log and skip; tell user the action requires elevated permissions |
| 404 | Resource not found | Re-fetch parent to verify IDs; retry once; if still 404 surface error |
| 409 | Conflict (duplicate action) | Treat as success (idempotent) |
| 429 | Rate limit | Wait `Retry-After` (default 10s); retry with exponential backoff |
| 500 | Trello server error | Retry up to 3× with backoff (1s, 2s, 4s); surface if all fail |
| 503 | Trello maintenance | Inform user; do not retry automatically |

### 12.2 Retry Policy

```
maxRetries:   3
backoff:      exponential — 1s, 2s, 4s
jitter:       ±200ms (to prevent thundering herd)
retryOn:      [429, 500, 502, 503, 504]
noRetryOn:    [400, 401, 403, 404]
```

### 12.3 Partial Failure Handling

For multi-step flows (e.g., create card + add checklist + assign member), if a later step fails the agent must:
1. Report which steps succeeded and which failed.
2. Offer to retry the failed step only.
3. Never silently swallow errors.

---

## 13. Data Models

### Board
```typescript
interface Board {
  id:             string;
  name:           string;
  desc:           string;
  closed:         boolean;
  url:            string;
  idOrganization: string | null;
  prefs: {
    background:   string;
    permissionLevel: "private" | "org" | "public";
  };
}
```

### List
```typescript
interface List {
  id:      string;
  name:    string;
  closed:  boolean;
  pos:     number;
  idBoard: string;
}
```

### Card
```typescript
interface Card {
  id:           string;
  name:         string;
  desc:         string;
  closed:       boolean;
  idList:       string;
  idBoard:      string;
  pos:          number;
  due:          string | null;      // ISO 8601
  dueComplete:  boolean;
  start:        string | null;      // ISO 8601
  idChecklists: string[];
  idMembers:    string[];
  idLabels:     string[];
  url:          string;
  shortUrl:     string;
  address:      string | null;
  coordinates:  string | null;
}
```

### Checklist
```typescript
interface Checklist {
  id:         string;
  name:       string;
  idCard:     string;
  idBoard:    string;
  pos:        number;
  checkItems: CheckItem[];
}
```

### CheckItem
```typescript
interface CheckItem {
  id:          string;
  name:        string;
  state:       "complete" | "incomplete";
  pos:         number;
  idChecklist: string;
  due:         string | null;
  idMember:    string | null;
}
```

### Label
```typescript
interface Label {
  id:      string;
  name:    string;
  color:   string | null;
  idBoard: string;
}
```

### Action (Comment / Event)
```typescript
interface Action {
  id:                string;
  type:              string;
  date:              string;
  idMemberCreator:   string;
  data: {
    text?:           string;
    card?:           { id: string; name: string };
    listBefore?:     { id: string; name: string };
    listAfter?:      { id: string; name: string };
    checkItem?:      { id: string; name: string; state: string };
  };
  memberCreator: {
    id:         string;
    username:   string;
    fullName:   string;
  };
}
```

### CustomField (Board-level definition)
```typescript
interface CustomField {
  id:                string;
  name:              string;
  type:              "text" | "number" | "date" | "checkbox" | "list";
  idBoard:           string;
  pos:               number;
  display:           { cardFront: boolean };
  options?:          CustomFieldOption[];   // only for type "list"
}

interface CustomFieldOption {
  id:    string;
  value: { text: string };
  color: string | null;
  pos:   number;
}
```

### CustomFieldItem (Card-level value)
```typescript
interface CustomFieldItem {
  id:             string;
  idCustomField:  string;
  idModel:        string;     // cardId
  modelType:      "card";
  value?:         { text?: string; number?: string; date?: string; checked?: string };
  idValue?:       string;     // for list type
}
```

### Webhook
```typescript
interface Webhook {
  id:          string;
  description: string;
  idModel:     string;
  callbackURL: string;
  active:      boolean;
  consecutiveFailures: number;
  firstConsecutiveFailDate: string | null;
}
```

### Notification
```typescript
interface Notification {
  id:     string;
  type:   string;
  unread: boolean;
  date:   string;
  data: {
    card?:    { id: string; name: string };
    board?:   { id: string; name: string };
    text?:    string;
  };
  memberCreator: { id: string; username: string; fullName: string };
}
```

---

## 14. Agent Reasoning Protocol

### 14.1 Plan-Before-Act

Before executing any mutation, the agent produces an internal plan:

```
INTENT:    CARD_MOVE
SLOTS:     card="Payment bug on mobile", targetList="In Progress"
RESOLVED:  cardId=c2, targetListId=list2
CHECKS:
  - card.idList (list1 "Backlog") ≠ list2 ("In Progress") → proceed
  - confirm_mutations=true → prompt user
PLAN:
  Step 1: PUT /cards/c2  Body: { idList: "list2" }
  Step 2: POST /cards/c2/actions/comments  Body: { text: "Moved to In Progress by agent." }
```

If `dry_run: true`, the agent stops after printing the plan and does not execute.

### 14.2 Confirmation Prompt

For any mutation with `confirm_mutations: true`:

> I'm about to **move "Payment bug on mobile"** from Backlog → In Progress and leave a comment.
> Confirm? (yes / no / show plan)

### 14.3 Action Trace

After execution, the agent produces a trace for transparency:

```
✓ PUT /cards/c2  →  200 OK  (moved to In Progress)
✓ POST /cards/c2/actions/comments  →  200 OK  (comment posted)
```

### 14.4 Capability Negotiation

If the user requests a capability that is out of scope for v3 (e.g., file attachment upload, Power-Up data, OAuth flow), the agent must:
1. Acknowledge the limitation clearly.
2. Suggest the closest available alternative if one exists.
3. Never silently attempt an unsupported operation.

---

## 15. Testing & Validation Matrix

### 15.1 Intent Classification Tests

| Input | Expected Intent | Expected Slots |
|-------|----------------|----------------|
| "what's due this week" | `QUERY_DUE_THIS_WEEK` | — |
| "move design card to review" | `CARD_MOVE` | card="design", list="review" |
| "add alice to the launch card" | `CARD_ASSIGN_MEMBER` | member="alice", card="launch" |
| "check off wireframes on onboarding" | `CHECKITEM_CHECK` | item="wireframes", card="onboarding" |
| "create a card called write docs in backlog" | `CARD_CREATE` | name="write docs", list="backlog" |
| "summarize the board" | `QUERY_BOARD_SUMMARY` | — |
| "set priority to high on the deploy card" | `CUSTOM_FIELD_SET` | field="priority", value="high", card="deploy" |
| "register webhook https://myapp.com/trello on this board" | `WEBHOOK_CREATE` | url="https://myapp.com/trello" |
| "show what bob is working on" | `QUERY_MEMBER_CARDS` | member="bob" |
| "delete the payment card" | `CARD_DELETE` | card="payment" |

### 15.2 API Correctness Tests

| Scenario | Assertion |
|---------|-----------|
| Move card to same list | Agent detects idempotency, skips API call, responds "already there" |
| Mark already-complete item complete | Agent skips, responds "already complete" |
| Set custom field — dropdown type | Uses `idValue` not `value` |
| Set custom field — text type | Uses `{ value: { text: "..." } }` |
| Check item state update | Uses `/cards/{cardId}/checkItem/{checkItemId}` not `/checklists/...` |
| Create card missing list name | Agent asks for clarification before calling POST |
| 429 response | Agent waits 10s, retries, succeeds |
| 404 on card | Agent re-fetches board cards, retries, surfaces if still 404 |

### 15.3 NLP Edge Cases

| Input | Expected Behavior |
|-------|------------------|
| "it" / "that card" / "this task" | Resolve to `lastMentionedCard` |
| Ambiguous card name (2+ matches) | Disambiguation prompt |
| Unknown member name | Disambiguation prompt with board members |
| Relative date "end of month" | Resolve to last day of current month |
| "mark everything in backlog as done" | Bulk operation: confirm count before proceeding |
| Mixed intent: "move and comment on the design card" | Decompose into `CARD_MOVE` + `CARD_ADD_COMMENT` |

---

## 16. Out of Scope for v3

- **Webhook ingestion / SSE**: The agent can register webhooks but does not host a listener endpoint.
- **File attachment upload**: Binary multipart uploads are not supported; URL attachments are.
- **Power-Up data / storage**: Reading or writing Power-Up plugin data.
- **Custom Board Backgrounds**: Setting backgrounds via binary upload.
- **Board templates**: Creating or cloning boards from a template.
- **Butler / automation rules**: Managing Trello's built-in automation.
- **OAuth 2.0 flow**: Token acquisition via OAuth redirect. API Key + Token assumed.
- **Enterprise endpoints**: Admin-level organization management.
- **Stickers on cards**: Reading or writing card stickers.
- **Aging / card covers**: Visual card prefs.

---

## 17. Open Questions

| # | Question | Owner | Target Resolution |
|---|---------|-------|------------------|
| OQ-01 | Should the agent support multi-board operations in a single session (e.g., "move card from Board A to Board B")? If so, how do listMaps merge? | Product | v3.1 |
| OQ-02 | What is the preferred confirmation UX — inline yes/no text or structured buttons? Impacts UI layer contract. | Design | Pre-launch |
| OQ-03 | Should `dry_run` mode be a persistent setting or a per-message prefix ("preview: move …")? | Product | Pre-launch |
| OQ-04 | For the search node, should results be limited to the active board or span all accessible boards by default? | Product | Pre-launch |
| OQ-05 | Custom field type `date` on cards — should the agent apply the same relative date parsing as card due dates? | Engineering | v3 |
| OQ-06 | How should the agent handle checklist items that themselves have due dates and member assignments (introduced in newer Trello)? | Engineering | v3.1 |
| OQ-07 | Token rotation strategy: if the API Token is revoked mid-session, should the agent surface a re-auth flow or hard-halt? | Engineering | v3 |
| OQ-08 | Should bulk operations ("mark all cards in Backlog as done") require per-card confirmation or a single "confirm N cards?" prompt? | Product | Pre-launch |

---

*End of PRD v3.0*