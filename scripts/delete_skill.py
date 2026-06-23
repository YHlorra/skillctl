#!/usr/bin/env python3
"""
Skill Manager - Delete Skill Module

删除一个 skill 目录。

Path resolution (first match wins):
  1. argv[2] if provided
  2. SKILLCTL_AGENT_DIR env var
  3. user.json scan_paths[0] (resolved by user_config.resolve_agent_skills_dir)
  4. Generic default ~/.claude/skills (with a warning)

Usage:
  python delete_skill.py <skill_name>
  python delete_skill.py <skill_name> <skills_root>
"""

import os
import sys
import shutil
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


def delete_skill(skills_root: Path, skill_name: str) -> bool:
    skill_dir = skills_root / skill_name
    if not skill_dir.exists():
        print(f"Error: Skill '{skill_name}' not found at {skill_dir}")
        return False
    try:
        shutil.rmtree(skill_dir)
        print(f"Successfully deleted skill: {skill_name}")
        return True
    except Exception as e:
        print(f"Error deleting skill '{skill_name}': {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python delete_skill.py <skill_name> [skills_root]")
        print("       skills_root falls back to SKILLCTL_AGENT_DIR env, then user.json scan_paths[0]")
        sys.exit(1)

    name = sys.argv[1]
    root = _resolve_root(sys.argv[2] if len(sys.argv) > 2 else None)

    delete_skill(root, name)