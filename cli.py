"""Interactive terminal REPL for testing the Trello agent."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

# Allow `python -m trello_agent.cli` from parent directory (e.g. Documents)
_pkg_root = Path(__file__).resolve().parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from app.observability.cli_history import append_turn, clear_history, format_history_for_display, get_history_lines
from app.observability.logging_setup import setup_logging
from app.session.session_memory import empty_memory


def main() -> None:
    p = argparse.ArgumentParser(description="Trello agent CLI")
    p.add_argument(
        "--session",
        default=None,
        help="Session id for in-memory history (default: random uuid)",
    )
    p.add_argument("--trace", action="store_true", help="Print intent/tool/trace after each turn")
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG logs for app.* on stderr (more detail during startup)",
    )
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = p.parse_args()

    setup_logging(verbose=args.verbose)

    session = args.session or str(uuid.uuid4())
    trace = args.trace
    use_color = not args.no_color

    def c(msg: str, code: str = "") -> str:
        if not use_color or not code:
            return msg
        return f"\033[{code}m{msg}\033[0m"

    print(c(f"Session: {session}", "1;36"))
    print("Commands: /quit /reset /history /trace on|off")
    print()

    trace_on = trace
    _loaded_agent = False
    memory: dict = empty_memory()

    while True:
        try:
            line = input(c("> ", "1;32")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line == "/quit":
            break
        if line == "/reset":
            clear_history(session)
            memory = empty_memory()
            print("History and session memory cleared.")
            continue
        if line == "/history":
            print(format_history_for_display(session))
            continue
        if line.startswith("/trace"):
            parts = line.split()
            if len(parts) >= 2:
                trace_on = parts[1].lower() in ("on", "1", "true", "yes")
            else:
                trace_on = not trace_on
            print(f"trace = {trace_on}")
            continue

        hist = get_history_lines(session)
        append_turn(session, "user", line)

        if not _loaded_agent:
            print(
                "Loading agent (first message only; can take 10–60s on WSL + /mnt/c).",
                flush=True,
            )
            print(
                "  → Progress: stderr lines tagged [startup] (import/compile/run). "
                "Use: python cli.py --verbose for DEBUG in app.*",
                flush=True,
            )
            _loaded_agent = True

        from app.core.graph import invoke_agent

        out = invoke_agent(line, hist, memory=memory)
        answer = out.get("answer") or ""
        memory = out.get("memory") if isinstance(out.get("memory"), dict) else memory

        append_turn(session, "assistant", answer)
        print("="*50)
        print(c(answer, "0"))
        print("="*50)

        parsed = out.get("parsed_response") or {}
        ev = out.get("evaluation_result") or {}
        ent = out.get("entities") or {}
        err_msg = (out.get("error_message") or "").strip()
        clarification = isinstance(parsed, dict) and parsed.get("clarification")

        if trace_on and (clarification or out.get("needs_clarification")):
            amb = out.get("ambiguous_entities") or {}
            print(
                c(
                    f"  [trace] clarify=true intent={out.get('intent')} "
                    f"candidates={amb!s}",
                    "90",
                )
            )

        if trace_on:
            pt = out.get("plan_trace") or []
            last = pt[-1] if isinstance(pt, list) and pt else {}
            parsed = out.get("parsed_response") if isinstance(out.get("parsed_response"), dict) else {}
            plan_id = parsed.get("plan_id") if isinstance(parsed, dict) else None
            # Build entity summary
            parts: list[str] = [
                f"intent={out.get('intent')}",
                f"tool={out.get('selected_tool')}",
                f"eval={ev.get('status')}",
                f"retries={out.get('evaluation_retry_count')}",
            ]
            if plan_id or (isinstance(last, dict) and last.get("step_id")):
                parts.append(
                    f"plan_id={plan_id!r} step={last.get('step_id')!r} "
                    f"agent={last.get('agent')!r} status={last.get('status')!r}",
                )
            if ent.get("card_name") or ent.get("card_id"):
                cid = str(ent.get("card_id") or "")
                parts.append(f"card={ent.get('card_name')!r}({cid[:8]}{'...' if len(cid) > 8 else ''})")
            if ent.get("list_name") or ent.get("list_id"):
                parts.append(f"list={ent.get('list_name')!r}")
            if ent.get("target_list_name") or ent.get("target_list_id"):
                parts.append(f"target_list={ent.get('target_list_name')!r}")
            if ent.get("resolved_board_name"):
                parts.append(f"board={ent.get('resolved_board_name')!r}")
            if err_msg:
                parts.append(f"err={err_msg[:80]!r}")
            if isinstance(last, dict) and last.get("http"):
                hops = last["http"]
                if isinstance(hops, list) and hops:
                    h = hops[-1]
                    if isinstance(h, dict):
                        parts.append(f"http={h.get('method')} {h.get('path')} -> {h.get('status')}")
            print(c("  [trace] " + " | ".join(parts), "90"))
        print()

    return None


if __name__ == "__main__":
    main()
    sys.exit(0)
