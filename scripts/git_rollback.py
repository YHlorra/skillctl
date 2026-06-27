#!/usr/bin/env python3
"""
Skill Manager - Git Rollback Module

单个 skill 的 git 仓库回滚，支持查看历史、选择版本、回滚。
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from _lib.paths import expand_path, is_symlink, resolve_symlink_target, is_git_repo

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))

def resolve_symlink_target(path: Path) -> Path:
    """Resolve symlink to real path."""
    try:
        return path.resolve()
    except OSError:
        return path

def get_git_log(path: Path, max_count: int = 20) -> List[Dict]:
    """Get git log for a repository."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "log",
                f"--max-count={max_count}",
                "--format=%H|%h|%s|%ad|%an",
                "--date=iso",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 5:
                commits.append(
                    {
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "message": parts[2],
                        "date": parts[3],
                        "author": parts[4],
                    }
                )
        return commits
    except Exception as e:
        print(f"Error getting git log: {e}")
        return []

def get_git_branches(path: Path) -> List[str]:
    """Get all branches in a repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "branch", "-a", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]
    except Exception:
        pass
    return []

def get_current_commit(path: Path) -> Optional[str]:
    """Get current commit hash."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def git_checkout(path: Path, commit_hash: str, create_backup: bool = True) -> bool:
    """Checkout a specific commit, optionally creating backup first."""
    try:
        # Check if it's a valid commit
        result = subprocess.run(
            ["git", "-C", str(path), "cat-file", "-t", commit_hash],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print(f"Error: {commit_hash} is not a valid commit")
            return False

        # Create backup of current state
        if create_backup:
            backup_dir = Path.home() / ".skill-manager" / "rollbacks"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            skill_name = path.name
            backup_path = backup_dir / f"{skill_name}_{timestamp}"
            shutil.copytree(path, backup_path, symlinks=False)
            print(f"Backup created: {backup_path}")

        # Perform checkout
        result = subprocess.run(
            ["git", "-C", str(path), "checkout", commit_hash, "--", "."],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"Checkout failed: {result.stderr}")
            return False

        # Stage changes
        subprocess.run(
            ["git", "-C", str(path), "add", "-A"], capture_output=True, timeout=10
        )

        # Create commit for rollback
        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", f"Rollback to {commit_hash[:8]}"],
            capture_output=True,
            timeout=10,
        )

        return True
    except Exception as e:
        print(f"Error during checkout: {e}")
        return False

def git_revert(path: Path, commit_hash: str) -> bool:
    """Revert to a specific commit without losing history."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "revert", "--no-commit", commit_hash],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False

        subprocess.run(
            ["git", "-C", str(path), "add", "-A"], capture_output=True, timeout=10
        )

        subprocess.run(
            ["git", "-C", str(path), "commit", "-m", f"Revert to {commit_hash[:8]}"],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception as e:
        print(f"Error during revert: {e}")
        return False

def git_reset_hard(path: Path, commit_hash: str, create_backup: bool = True) -> bool:
    """Hard reset to a specific commit."""
    try:
        if create_backup:
            backup_dir = Path.home() / ".skill-manager" / "rollbacks"
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            skill_name = path.name
            backup_path = backup_dir / f"{skill_name}_{timestamp}"
            shutil.copytree(path, backup_path, symlinks=False)
            print(f"Backup created: {backup_path}")

        subprocess.run(
            ["git", "-C", str(path), "reset", "--hard", commit_hash],
            capture_output=True,
            timeout=30,
        )
        return True
    except Exception as e:
        print(f"Error during reset: {e}")
        return False

def find_skill_path(skill_name: str, search_paths: List[Path]) -> Optional[Path]:
    """Find a skill directory by name in search paths."""
    for search_path in search_paths:
        if not search_path.exists():
            continue
        skill_path = search_path / skill_name
        if skill_path.exists():
            return skill_path
    return None

def get_commits(skill_path: Path, max_count: int = 20) -> List[Dict]:
    """Get commit history."""
    if not is_git_repo(skill_path):
        return []
    return get_git_log(skill_path, max_count)

def get_current_hash(skill_path: Path) -> Optional[str]:
    """Get current commit hash."""
    return get_current_commit(skill_path)

def rollback(skill_path: Path, commit_hash: str, mode: str = "checkout") -> bool:
    """Rollback to specified commit."""
    if not is_git_repo(skill_path):
        print(f"Error: {skill_path} is not a git repository")
        return False

    if mode == "checkout":
        return git_checkout(skill_path, commit_hash)
    elif mode == "revert":
        return git_revert(skill_path, commit_hash)
    elif mode == "reset":
        return git_reset_hard(skill_path, commit_hash)
    else:
        print(f"Unknown rollback mode: {mode}")
        return False

def interactive_rollback(skill_path: Path) -> bool:
    """Interactively select a commit to rollback to."""
    commits = get_commits(skill_path)
    current_hash = get_current_hash(skill_path)

    if not commits:
        print("No commits found or not a git repository")
        return False

    print(f"\n{'=' * 70}")
    print(f"Git History: {skill_path.name}")
    print(f"Current: {current_hash[:8] if current_hash else 'unknown'}")
    print(f"{'=' * 70}")
    print(f"{'#':<4} {'Hash':<10} {'Date':<26} {'Author':<16} Message")
    print("-" * 70)

    for i, commit in enumerate(commits, 1):
        marker = (
            "→ "
            if commit["hash"][:8] == (current_hash[:8] if current_hash else "")
            else "  "
        )
        date_short = commit["date"][:19]
        msg = (
            commit["message"][:40] + "..."
            if len(commit["message"]) > 40
            else commit["message"]
        )
        print(
            f"{marker}{i:<4} {commit['short_hash']:<10} {date_short:<26} {commit['author']:<16} {msg}"
        )

    print("-" * 70)
    print("[R] Rollback to selected commit")
    print("[Q] Quit without changes")

    choice = input("\nSelect commit number to rollback (or R/Q): ").strip().upper()

    if choice == "Q":
        print("Cancelled")
        return False
    elif choice == "R":
        num = input("Enter commit number: ").strip()
        if num.isdigit() and 1 <= int(num) <= len(commits):
            commit = commits[int(num) - 1]
            return rollback(commit["hash"], mode="checkout")
    elif choice.isdigit() and 1 <= int(choice) <= len(commits):
        commit = commits[int(choice) - 1]
        confirm = (
            input(
                f"Rollback to {commit['short_hash']} - {commit['message'][:50]}? [y/N]: "
            )
            .strip()
            .lower()
        )
        if confirm == "y":
            return rollback(commit["hash"], mode="checkout")

    return False

def main():
    parser = argparse.ArgumentParser(description="Git rollback for skills")
    parser.add_argument(
        "--skill", "-s", type=str, help="Skill name (will search in default paths)"
    )
    parser.add_argument("--path", "-p", type=str, help="Direct path to skill directory")
    parser.add_argument(
        "--index", "-i", type=str, help="Path to index.json for skill lookup"
    )
    parser.add_argument("--list", "-l", action="store_true", help="List commit history")
    parser.add_argument("--commit", "-c", type=str, help="Commit hash to rollback to")
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        choices=["checkout", "revert", "reset"],
        default="checkout",
        help="Rollback mode (default: checkout)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively select commit to rollback to",
    )

    args = parser.parse_args()

    # Determine skill path
    skill_path = None
    skill_name = None

    if args.path:
        skill_path = expand_path(args.path)
        skill_name = skill_path.name
    elif args.skill:
        skill_name = args.skill
        # Search in default paths
        home = Path.home()
        search_paths = [
            home / ".claude" / "skills",
            home / ".agents" / "skills",
            Path.cwd() / ".claude" / "skills",
        ]
        skill_path = find_skill_path(args.skill, search_paths)
        if not skill_path:
            # Try index
            if args.index and Path(args.index).exists():
                skill_path = find_skill_path(args.skill, [])
    else:
        print("Error: Either --skill or --path required")
        return 1

    if not skill_path:
        print(f"Error: Could not find skill: {skill_name or args.skill}")
        return 1

    if is_symlink(skill_path):
        skill_path = resolve_symlink_target(skill_path)

    # Check if git repo
    if not is_git_repo(skill_path):
        print(f"Warning: {skill_path} is not a git repository")
        print("Git rollback requires the skill to have a .git directory")
        return 1

    index_path = Path(args.index) if args.index else None

    rollbacker = GitRollbacker(
        skill_path=skill_path, skill_name=skill_name, index_path=index_path
    )

    if args.interactive or (not args.commit and not args.list):
        # Interactive mode
        success = interactive_rollback(skill_path)
        if success:
            print("Rollback completed successfully")
        return 0 if success else 1

    elif args.list:
        # List commits
        commits = get_commits(skill_path)
        current = get_current_hash(skill_path)
        print(f"\nGit History: {skill_path.name}")
        print(f"Current: {current[:8] if current else 'unknown'}")
        print("-" * 60)
        for commit in commits:
            print(
                f"{commit['short_hash']} | {commit['date'][:19]} | {commit['message']}"
            )
        return 0

    elif args.commit:
        # Rollback to specific commit
        print(f"Rolling back {skill_path.name} to {args.commit}")
        success = rollback(skill_path, args.commit, mode=args.mode)
        if success:
            print("Rollback completed successfully")
        return 0 if success else 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
