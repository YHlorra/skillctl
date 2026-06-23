#!/usr/bin/env python3
"""
Skill Manager - Check Updates Module

检测 skills 的远程 Git 更新。对比 index.json 中记录的本地 hash 与远程 hash，
报告哪些 skill 有可用更新。

Usage:
    python check_updates.py                      # Check all skills with updates
    python check_updates.py --skill <name>       # Check single skill
    python check_updates.py --json              # Output JSON format
    python check_updates.py --fetch             # Fetch remote refs before checking
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class UpdateInfo:
    """Information about a skill update."""
    skill_name: str
    skill_path: str
    current_hash: str
    remote_hash: str
    branch: str
    commits_behind: int
    has_update: bool
    remote_url: str


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def get_remote_hash(git_url: str, branch: str = "HEAD", timeout: int = 30) -> Optional[str]:
    """Get the hash of a remote branch using git ls-remote."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", git_url, f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout:
            # Output format: "<hash>\t<ref>"
            parts = result.stdout.strip().split()
            if parts:
                return parts[0]
    except Exception:
        pass
    return None


def get_remote_info(git_url: str, timeout: int = 30) -> Dict[str, Optional[str]]:
    """Get all remote branch hashes."""
    info = {"default_branch": None, "main_hash": None, "master_hash": None}

    if not git_url:
        return info

    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", git_url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    hash_val = parts[0]
                    ref_name = parts[1]  # refs/heads/main or refs/heads/master
                    branch = ref_name.replace("refs/heads/", "")

                    if branch in ("main", "master"):
                        if info["default_branch"] is None:
                            info["default_branch"] = branch
                        if branch == "main":
                            info["main_hash"] = hash_val
                        elif branch == "master":
                            info["master_hash"] = hash_val

    except Exception:
        pass

    return info


def check_skill_update(skill_data: Dict, index_path: Path) -> UpdateInfo:
    """Check if a skill has updates available."""
    skill_name = skill_data.get("name", "unknown")
    locations = skill_data.get("locations", [])
    git_info = skill_data.get("git", {})
    metadata = skill_data.get("metadata", {})

    # Get the first real (non-symlink) location
    real_location = None
    for loc in locations:
        if not loc.get("is_symlink", False):
            real_location = loc
            break

    if not real_location:
        real_location = locations[0] if locations else {}

    skill_path = real_location.get("path", "unknown")
    current_hash = git_info.get("current_hash", "none")
    remote_url = git_info.get("remote_url") or metadata.get("github_url")
    branch = git_info.get("branch", "main")

    if not remote_url:
        return UpdateInfo(
            skill_name=skill_name,
            skill_path=skill_path,
            current_hash=current_hash or "none",
            remote_hash="no-remote",
            branch=branch or "main",
            commits_behind=0,
            has_update=False,
            remote_url="",
        )

    # Get remote hash
    if not branch:
        branch = "main"

    remote_hash = get_remote_hash(remote_url, branch)

    if not remote_hash:
        return UpdateInfo(
            skill_name=skill_name,
            skill_path=skill_path,
            current_hash=current_hash or "none",
            remote_hash="unknown",
            branch=branch,
            commits_behind=-1,  # Indicates couldn't fetch
            has_update=False,
            remote_url=remote_url,
        )

    # Calculate commits behind
    commits_behind = 0
    if current_hash and remote_hash and current_hash != remote_hash:
        try:
            # Create a temp dir for comparison if skill is not a git repo
            skill_path_obj = expand_path(skill_path)
            if (skill_path_obj / ".git").exists():
                # Use local git to count
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(skill_path_obj),
                        "rev-list",
                        "--ancestry-path",
                        f"{remote_hash}..{current_hash}",
                        "--count",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    commits_behind = int(result.stdout.strip())
        except Exception:
            pass

    has_update = current_hash != remote_hash and current_hash != "none"

    return UpdateInfo(
        skill_name=skill_name,
        skill_path=skill_path,
        current_hash=current_hash or "none",
        remote_hash=remote_hash,
        branch=branch,
        commits_behind=commits_behind,
        has_update=has_update,
        remote_url=remote_url,
    )


def load_index(index_path: Path) -> Dict:
    """Load index.json."""
    if not index_path.exists():
        print(f"Error: index.json not found at {index_path}", file=sys.stderr)
        return {}

    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_all_updates(
    index_path: Path,
    skill_name: Optional[str] = None,
    fetch_remote: bool = False,
) -> List[UpdateInfo]:
    """Check all skills for updates."""
    index = load_index(index_path)
    if not index:
        return []

    updates = []
    skills = index.get("skills", {})

    # If fetching, run git fetch on all skills first
    if fetch_remote:
        print("Fetching remote refs for all skills...")

    for name, skill_data in skills.items():
        if skill_name and name != skill_name:
            continue

        update_info = check_skill_update(skill_data, index_path)
        updates.append(update_info)

        if fetch_remote and update_info.remote_url:
            # Background fetch for next time
            skill_path = expand_path(update_info.skill_path)
            if (skill_path / ".git").exists():
                subprocess.Popen(
                    ["git", "-C", str(skill_path), "fetch", "--quiet"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    return updates


def print_updates_table(updates: List[UpdateInfo], show_all: bool = False):
    """Print updates in a formatted table."""
    # Filter
    if not show_all:
        updates = [u for u in updates if u.has_update]

    if not updates:
        print("\n✓ All skills are up to date!")
        return

    # Sort by skill name
    updates.sort(key=lambda x: x.skill_name)

    print(f"\n{'=' * 90}")
    print(f" Skills with Available Updates ({len(updates)} found)")
    print(f"{'=' * 90}")
    print(
        f"{'Skill':<30} {'Current':<10} {'Remote':<10} {'Branch':<10} {'Behind':<8} {'Path'}"
    )
    print("-" * 90)

    for u in updates:
        behind_str = (
            str(u.commits_behind) if u.commits_behind >= 0 else "?"
        )
        print(
            f"{u.skill_name:<30} {u.current_hash[:8]:<10} {u.remote_hash[:8]:<10} "
            f"{u.branch:<10} {behind_str:<8} {u.skill_path}"
        )

    print("-" * 90)
    print("\nTo update a skill, use:")
    print("  python git_rollback.py --skill <name> --interactive")


def print_updates_json(updates: List[UpdateInfo]):
    """Print updates as JSON."""
    output = {
        "check_time": datetime.now().isoformat(),
        "total_skills": len(updates),
        "with_updates": sum(1 for u in updates if u.has_update),
        "skills": [asdict(u) for u in updates],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


def update_wrapper_repos(
    library_root: Path,
    execute: bool = True,
    dry_run: bool = False,
    fetch_timeout: int = 60,
) -> dict:
    """Update every direct-child git repo under library_root.

    Iterates filesystem (not index). Catches both wrapper repos (multi-skill)
    and per-skill .git installs. Per-repo errors are recorded but never
    abort the batch.

    Args:
        library_root: canonical library path (from get_canonical_path)
        execute: True to actually run git pull; False to only record candidates
        dry_run: True to skip the actual pull even if execute is True
        fetch_timeout: per-repo fetch/pull timeout in seconds

    Returns dict with:
    - repos_found: int (direct children with .git/)
    - pulled: [{repo, output}]  (successful pulls)
    - would_pull: [repo_name]    (dry-run or no-remote-skipped)
    - skipped: [{repo, reason}]  (no remote, worktree marker, etc.)
    - errors: [{repo, stderr}]   (dirty, conflict, timeout, network)
    """
    summary = {
        "repos_found": 0,
        "pulled": [],
        "would_pull": [],
        "skipped": [],
        "errors": [],
    }

    if not library_root.exists():
        summary["errors"].append(
            {"repo": str(library_root), "stderr": "library_root does not exist"}
        )
        return summary

    for child in sorted(library_root.iterdir()):
        if not child.is_dir():
            continue

        git_path = child / ".git"
        if not git_path.exists():
            continue

        # Skip worktree markers (.git is a file, not a directory)
        if git_path.is_file():
            summary["skipped"].append({"repo": child.name, "reason": "worktree marker"})
            continue

        summary["repos_found"] += 1

        # Check remote
        try:
            remote_proc = subprocess.run(
                ["git", "-C", str(child), "remote", "-v"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            summary["errors"].append({"repo": child.name, "stderr": "remote check timeout"})
            continue
        except Exception as e:
            summary["errors"].append({"repo": child.name, "stderr": f"remote check failed: {e}"})
            continue

        if remote_proc.returncode != 0 or not remote_proc.stdout.strip():
            summary["skipped"].append({"repo": child.name, "reason": "no remote"})
            continue

        if dry_run or not execute:
            summary["would_pull"].append(child.name)
            continue

        # Actually fetch + pull
        try:
            fetch_proc = subprocess.run(
                ["git", "-C", str(child), "fetch", "--all", "--prune"],
                capture_output=True,
                text=True,
                timeout=fetch_timeout,
            )
            if fetch_proc.returncode != 0:
                summary["errors"].append(
                    {"repo": child.name, "stderr": f"fetch failed: {fetch_proc.stderr.strip()}"}
                )
                continue

            pull_proc = subprocess.run(
                ["git", "-C", str(child), "pull", "--ff-only"],
                capture_output=True,
                text=True,
                timeout=fetch_timeout,
            )
            if pull_proc.returncode == 0:
                summary["pulled"].append(
                    {"repo": child.name, "output": pull_proc.stdout.strip()}
                )
            else:
                summary["errors"].append(
                    {"repo": child.name, "stderr": pull_proc.stderr.strip()}
                )
        except subprocess.TimeoutExpired:
            summary["errors"].append({"repo": child.name, "stderr": "fetch/pull timeout"})
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else str(e)
            summary["errors"].append({"repo": child.name, "stderr": stderr})
        except Exception as e:
            summary["errors"].append({"repo": child.name, "stderr": f"unexpected: {e}"})

    return summary


def print_repos_summary(summary: dict):
    """Pretty-print the result of update_wrapper_repos."""
    print(f"\n{'=' * 70}")
    print(f" Wrapper-repo update: {summary['repos_found']} git repo(s) found")
    print(f"{'=' * 70}")

    if not summary["repos_found"]:
        print(
            "\nNo git repos found. Run 'skillctl install <github-url>' to add one."
        )
        return

    if summary["pulled"]:
        print(f"\n✓ Pulled ({len(summary['pulled'])}):")
        for item in summary["pulled"]:
            print(f"  - {item['repo']}")

    if summary["would_pull"]:
        print(f"\n→ Would pull ({len(summary['would_pull'])}):")
        for name in summary["would_pull"]:
            print(f"  - {name}")

    if summary["skipped"]:
        print(f"\n→ Skipped ({len(summary['skipped'])}):")
        for item in summary["skipped"]:
            print(f"  - {item['repo']}  ({item['reason']})")

    if summary["errors"]:
        print(f"\n✗ Errors ({len(summary['errors'])}):")
        for item in summary["errors"]:
            # Truncate long stderr
            err = item["stderr"]
            if len(err) > 200:
                err = err[:197] + "..."
            print(f"  - {item['repo']}: {err}")


def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - Check for Git Remote Updates"
    )
    parser.add_argument(
        "--index", "-i", type=str, help="Path to index.json"
    )
    parser.add_argument(
        "--skill", "-s", type=str, help="Check specific skill only"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--fetch", "-f", action="store_true", help="Fetch remote refs before checking"
    )
    parser.add_argument(
        "--all", "-a", action="store_true", help="Show all skills, not just those with updates"
    )
    parser.add_argument(
        "--nested", "-n", action="store_true", help="Include nested Git repos"
    )
    parser.add_argument(
        "--repos",
        action="store_true",
        help="Update every direct-child git repo under library root "
        "(wrapper repos + per-skill git installs). Mutually exclusive with --skill.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="With --repos: actually run 'git fetch && git pull --ff-only'. "
        "Default for --repos is live (fetch + pull); pass --dry-run to preview.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --repos: show what would be pulled without running git pull.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-repo fetch/pull timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--library",
        type=str,
        help="Library root path (default: SKILL_LIBRARY_PATH env or skillctl canonical)",
    )

    args = parser.parse_args()

    # --repos path: filesystem-driven update of wrapper repos / per-skill .git
    # Mutually exclusive with --skill (the existing per-skill path)
    if args.repos:
        if args.skill:
            print(
                "Error: --repos and --skill are mutually exclusive. "
                "Use --repos for filesystem-driven update, --skill for index-driven.",
                file=sys.stderr,
            )
            return 2

        # Resolve library root: --library > SKILL_LIBRARY_PATH > skillctl canonical
        if args.library:
            library_root = expand_path(args.library)
        else:
            env_lib = os.environ.get("SKILL_LIBRARY_PATH")
            if env_lib:
                library_root = expand_path(env_lib)
            else:
                # Fall back to skillctl's own directory's parent
                script_dir = Path(__file__).parent
                library_root = (script_dir.parent.parent).resolve()

        summary = update_wrapper_repos(
            library_root=library_root,
            execute=True,  # default: live pull
            dry_run=args.dry_run,
            fetch_timeout=args.timeout,
        )
        print_repos_summary(summary)
        # Exit 1 if any errors so callers / CI can detect
        return 1 if summary["errors"] else 0

    # Find index.json
    if args.index:
        index_path = expand_path(args.index)
    else:
        # Default to skillctl/index.json
        script_dir = Path(__file__).parent
        skillctl_dir = script_dir.parent
        index_path = skillctl_dir / "index.json"

    if not index_path.exists():
        print(f"Error: index.json not found at {index_path}", file=sys.stderr)
        print("\nHint: Run 'python scan_and_index.py' first to generate index.json")
        return 1

    # Check updates
    updates = check_all_updates(index_path, args.skill, args.fetch)

    if not updates:
        print("No skills found to check.")
        return 0

    # Filter nested if not requested
    if not args.nested:
        index = load_index(index_path)
        nested_paths = set(n["repo_path"] for n in index.get("nested_repos", []))
        updates = [u for u in updates if u.skill_path not in nested_paths]

    # Output
    if args.json:
        print_updates_json(updates)
    else:
        print_updates_table(updates, show_all=args.all)

    # Return exit code based on updates
    if any(u.has_update for u in updates):
        return 1  # Has updates available
    return 0


if __name__ == "__main__":
    sys.exit(main())