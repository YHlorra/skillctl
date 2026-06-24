"""TTY-aware interactive helpers, shared across L2 scripts."""
from __future__ import annotations

import sys


def should_prompt_user(non_interactive: bool) -> bool:
    """Decide whether to prompt the user.

    Returns False if --non-interactive flag is set OR stdin is not a TTY.
    Auto-detecting non-TTY prevents hangs when invoked by LLM agents or in pipes.
    """
    if non_interactive:
        return False
    if not sys.stdin.isatty():
        return False
    return True


def prompt_user_confirm(question: str) -> bool:
    """Interactive y/N prompt. Returns True iff user explicitly confirmed.

    Handles EOFError and KeyboardInterrupt as "no".
    """
    try:
        answer = input(f"{question} [y/N]: ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
