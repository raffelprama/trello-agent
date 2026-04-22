"""AnswerAgent — system and user prompts for final user-facing replies."""

from __future__ import annotations

ANSWER_SYSTEM = (
    "Be accurate and clear. Ground every factual claim in the AUTHORITATIVE "
    "JSON only. Leave a little breathing room: short paragraphs and spacing "
    "between sections when listing multiple boards, lists, or cards."
)

ANSWER_USER_TEMPLATE = """Summarize the Trello result for the user's latest question.

CURRENT user question (answer this): {question}
Plan intent: {intent}

AUTHORITATIVE data for this turn only (JSON):
{blob}

Prior conversation (context only — do NOT invent boards/cards from it):
{history_text}

Rules:
- Ground every factual claim in the JSON. If cards/lists/boards are listed, reflect counts and names accurately.
- If the user asked to see all cards on a board, list or summarize cards from the "cards" array.
- If "card" is present, summarize description, labels, due dates, checklists, members.
- If "dry_run" is true in the JSON, say clearly that mutating API calls were not executed and name dry_run_stopped_at if present.
- If clarification is true, the assistant is only asking a question — repeat it politely.
- Do not invent IDs.
- Format for readability: use short paragraphs and a blank line between sections when you cover several topics (e.g. board name, then lists, then cards). Avoid a single wall of text when there are many items.
- If it return several cards, lists, or boards, use a blank line between each section (like use point point).
"""


def format_answer_user(*, question: str, intent: str, blob: str, history_text: str) -> str:
    return ANSWER_USER_TEMPLATE.format(
        question=question,
        intent=intent,
        blob=blob,
        history_text=history_text,
    )
