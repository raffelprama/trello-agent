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

from app.cli_history import append_turn, clear_history, format_history_for_display, get_history_lines
from app.logging_setup import setup_logging


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
            print("History cleared.")
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

        from app.graph import invoke_agent

        out = invoke_agent(line, hist)
        answer = out.get("answer") or ""

        append_turn(session, "assistant", answer)
        print(c(answer, "0"))

        if trace_on:
            ev = out.get("evaluation_result") or {}
            print(
                c(
                    f"  [trace] intent={out.get('intent')} tool={out.get('selected_tool')} "
                    f"eval={ev.get('status')} retries={out.get('evaluation_retry_count')}",
                    "90",
                )
            )
        print()

    return None


if __name__ == "__main__":
    main()
    sys.exit(0)
