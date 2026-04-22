"""ReflectionAgent — system and user prompts for failure explanations."""

from __future__ import annotations

REFLECTION_SYSTEM = "Be concise and helpful."

REFLECTION_USER_TEMPLATE = """The Trello assistant could not complete the request.
Explain briefly what went wrong and what the user could try next.

User question: {question}
Error: {err}
Evaluation: {eval_reason}
Plan trace (last steps): {trace_snippet}

If something was not found, suggest checking spelling or listing available boards/lists from a prior successful turn.
"""


def format_reflection_user(*, question: str, err: str, eval_reason: str, trace_snippet: str) -> str:
    return REFLECTION_USER_TEMPLATE.format(
        question=question,
        err=err,
        eval_reason=eval_reason,
        trace_snippet=trace_snippet,
    )
