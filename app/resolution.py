"""Name resolution — exact, prefix, substring, then Levenshtein ≤2 single candidate (PRD §5.1)."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def best_match_by_name(
    name_hint: str,
    rows: list[T],
    *,
    get_name: Callable[[T], str],
    max_levenshtein: int = 2,
) -> T | None:
    """Return unique row by exact → prefix → substring → Levenshtein tier."""
    if not name_hint or not rows:
        return None
    nh = " ".join(name_hint.strip().lower().split())
    names: list[tuple[T, str]] = []
    for r in rows:
        n = " ".join(get_name(r).strip().lower().split())
        names.append((r, n))
    exact = [r for r, n in names if n == nh]
    if len(exact) == 1:
        return exact[0]
    starts = [r for r, n in names if n.startswith(nh) and nh]
    if len(starts) == 1:
        return starts[0]
    subs = [r for r, n in names if nh in n]
    if len(subs) == 1:
        return subs[0]
    lev_cand = [r for r, n in names if levenshtein(nh, n) <= max_levenshtein]
    if len(lev_cand) == 1:
        return lev_cand[0]
    return None


def match_dicts_by_name(
    name_hint: str,
    dicts: list[dict[str, Any]],
    name_key: str = "name",
) -> dict[str, Any] | None:
    return best_match_by_name(name_hint, [d for d in dicts if isinstance(d, dict)], get_name=lambda d: str(d.get(name_key, "")))
