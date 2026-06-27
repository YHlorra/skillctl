#!/usr/bin/env python3
"""
Skill Manager - Delete Skill Module

Irreversibly delete a skill. NO backup is created. User is expected to
cp -mv first if they want a safety net.

Path resolution (first match wins):
  1. --root argv
  2. SKILLCTL_AGENT_DIR env var
  3. user.json scan_paths[0] (resolved by user_config.resolve_agent_skills_dir)
  4. Generic default ~/.claude/skills (with a warning)

Usage:
  python delete_skill.py <skill_name> [--root PATH] [--yes]
  python scripts/skillctl.py delete --skill <skill_name> [--root PATH] [--yes]
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path


def _resolve_root(argv_root: str | None) -> Path:
    """Resolve the skills root from argv / env / user.json / default."""
    if argv_root:
        return Path(os.path.expandvars(os.path.expanduser(argv_root)))

    # Local import: user_config is sibling module
    try:
        from user_config import resolve_agent_skills_dir

        resolved = resolve_agent_skills_dir()
        if resolved is not None:
            return resolved
    except ImportError:
        pass

    # Generic last-resort default — same on every machine, no leak
    default = Path("~/.claude/skills").expanduser()
    print(
        f"Warning: no SKILLCTL_AGENT_DIR or user.json configured; "
        f"falling back to generic default {default}. "
        f"See references/user-config.md to override.",
        file=sys.stderr,
    )
    return default


def _find_github_url(skills_root: Path, skill_name: str) -> str | None:
    """Best-effort lookup of skill's GitHub URL from index.json."""
    # Try canonical index location first
    index_paths = [
        skills_root / "index.json",
        Path(os.environ.get("SKILLCTL_INDEX", "")),
    ]
    for index_path in index_paths:
        if not index_path.exists():
            continue
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
            skills = index.get("skills", [])
            for entry in skills:
                if entry.get("name") == skill_name:
                    return entry.get("metadata", {}).get("github_url")
        except Exception:
            pass
    return None


def delete_skill(
    skills_root: Path, skill_name: str, *, yes: bool = False, confirm_window: int = 3
) -> bool:
    """
    Delete a skill irreversibly. No backup is created.

    Args:
        skills_root: Root directory containing skills.
        skill_name: Name of the skill to delete.
        yes: If True, skip the 3-second abort countdown.
        confirm_window: Countdown seconds before delete (default 3).

    Returns:
        True if deleted successfully, False otherwise.
    """
    skill_dir = skills_root / skill_name

    if not skill_dir.exists():
        print(f"Error: Skill '{skill_name}' not found at {skill_dir}")
        return False

    # Loud warning block
    print()
    print(f"  ⚠ PERMANENT DELETE: {skill_name}")
    print(f"    Path: {skill_dir}")
    print(f"    This skill will NOT be backed up.")
    print()

    # Best-effort GitHub URL lookup for post-delete notice
    github_url = _find_github_url(skills_root, skill_name)

    # 3-second abort window (skip if --yes or stdin not a TTY)
    if not yes and sys.stdin.isatty():
        for i in range(confirm_window, 0, -1):
            print(f"  Ctrl-C within {i}s to abort... ", end="\r", flush=True)
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n[delete] Aborted.")
                return False
        print(" " * 50, end="\r", flush=True)  # clear the countdown line

    # Perform deletion
    try:
        shutil.rmtree(skill_dir)
    except Exception as e:
        print(f"Error deleting skill '{skill_name}': {e}")
        return False

    # Post-delete notice
    print(f"  ✓ Deleted: {skill_name}")
    print(f"    Path: {skill_dir}")
    print(f"    No backup exists.")
    if github_url:
        print(f"    To restore: skillctl install {github_url}")
    else:
        print(f"    To restore: re-install manually from source.")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete a skill (irreversible — no backup)"
    )
    parser.add_argument("skill", help="Skill name to delete (positional)")
    parser.add_argument(
        "--root", help="Skills root (default: SKILLCTL_AGENT_DIR > user.json > ~/.claude/skills)"
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Skip 3s abort countdown"
    )

    args = parser.parse_args()
    skills_root = _resolve_root(args.root)

    success = delete_skill(skills_root, args.skill, yes=args.yes)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())