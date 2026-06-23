#!/usr/bin/env python3
"""
Skill Manager - Collect and Link Module

收集 skill 到目标目录，创建 symlink 管理全局和项目本地 skills。
基于 deduplicate.py 的决策文件执行实际操作。
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import subprocess

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def is_symlink(path: Path) -> bool:
    """Check if path is a symlink."""
    try:
        return path.is_symlink()
    except OSError:
        return False


def resolve_symlink_target(path: Path) -> Path:
    """Resolve symlink to real path."""
    try:
        return path.resolve()
    except OSError:
        return path


def create_backup(path: Path, backup_dir: Path) -> Optional[Path]:
    """Create backup of a directory before modification."""
    if not path.exists():
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{path.name}_{timestamp}"
    backup_path = backup_dir / backup_name

    try:
        shutil.copytree(path, backup_path, symlinks=False, dirs_exist_ok=False)
        print(f"  Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"  Warning: Backup failed: {e}")
        return None


def remove_symlink(path: Path) -> bool:
    """Remove a symlink (works on both Windows and Unix)."""
    try:
        if is_symlink(path):
            # On Windows, is_dir() returns True for symlinks to directories
            if path.is_dir() or (sys.platform == "win32" and not path.is_file()):
                os.rmdir(path)
            else:
                path.unlink()
            return True
    except Exception as e:
        print(f"  Error removing symlink {path}: {e}")
    return False


def create_symlink(source: Path, link: Path) -> bool:
    """Create a symlink from link to source."""
    try:
        # Ensure parent directory exists
        link.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing symlink or file if present
        if link.exists() or is_symlink(link):
            if is_symlink(link):
                link.unlink()
            elif link.is_dir() and not is_symlink(link):
                # It's a real directory, don't remove
                print(f"  Warning: {link} is a real directory, skipping")
                return False
            else:
                link.unlink()

        # Create symlink
        if sys.platform == "win32":
            # On Windows, symlinks require special handling
            # Use junction for directories if we don't have SeCreateSymbolicLinkPrivilege
            if source.is_dir():
                try:
                    os.symlink(str(source), str(link), target_is_directory=True)
                except OSError:
                    # Fallback: use junction on Windows via subprocess (more reliable in Git Bash)
                    subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(link), str(source)],
                        check=True,
                    )
            else:
                os.symlink(str(source), str(link))
        else:
            os.symlink(str(source), str(link))

        print(f"  Created symlink: {link} -> {source}")
        return True
    except Exception as e:
        print(f"  Error creating symlink: {e}")
        return False


def copy_skill(source: Path, target: Path, preserve_git: bool = True) -> bool:
    """Copy a skill directory to target location."""
    try:
        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing if present
        if target.exists():
            if is_symlink(target):
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        if preserve_git and (source / ".git").exists():
            # Use git clone for preserving git history
            subprocess.run(
                ["git", "clone", str(source), str(target)],
                capture_output=True,
                check=True,
            )
            print(f"  Cloned with git history: {source} -> {target}")
        else:
            # Regular copy
            shutil.copytree(source, target, symlinks=False, dirs_exist_ok=False)
            print(f"  Copied: {source} -> {target}")

        return True
    except Exception as e:
        print(f"  Error copying skill: {e}")
        return False


def is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository."""
    return (path / ".git").exists()


class SkillCollector:
    """Handles skill collection and symlink creation."""

    def __init__(self, index_path: Path, decisions_path: Path = None):
        self.index_path = index_path
        self.decisions_path = decisions_path

        with open(index_path, "r", encoding="utf-8") as f:
            self.index = json.load(f)

        if decisions_path and decisions_path.exists():
            with open(decisions_path, "r", encoding="utf-8") as f:
                self.decisions_data = json.load(f)
            self.decisions = self.decisions_data.get("decisions", {})
        else:
            self.decisions = {}
            self.decisions_data = None

        self.backup_dir = Path.home() / ".skill-manager" / "backups"
        self.results = {
            "collected": [],
            "symlinks_created": [],
            "symlinks_removed": [],
            "errors": [],
        }

    def collect_skill(
        self, skill_name: str, target_dir: Path, create_symlinks: bool = True, dry_run: bool = False
    ) -> bool:
        """Collect a single skill to target directory."""
        skill = self.index["skills"].get(skill_name)
        if not skill:
            print(f"Skill '{skill_name}' not found in index")
            return False

        # Get decision if exists
        decision = self.decisions.get(skill_name, {})
        keep_path = decision.get("keep")
        remove_paths = decision.get("remove", [])

        # Find the best source
        locations = skill["locations"]
        source_path = None

        if keep_path:
            source_path = expand_path(keep_path)
        else:
            # Find first non-symlink location
            for loc in locations:
                if not loc["is_symlink"]:
                    source_path = expand_path(loc["path"])
                    break

        if not source_path or not source_path.exists():
            if not dry_run:
                print(f"Source path not found: {source_path}")
                self.results["errors"].append(
                    {"skill": skill_name, "error": f"Source not found: {source_path}"}
                )
            return False

        # Check if source is already a symlink
        source_is_symlink = is_symlink(source_path)
        if source_is_symlink:
            source_path = resolve_symlink_target(source_path)

        # Determine target path
        target_skill_dir = target_dir / skill_name
        target_skill_dir = (
            target_skill_dir.resolve()
            if target_skill_dir.exists()
            else target_skill_dir
        )

        # Don't collect if source and target are the same
        if source_path.resolve() == target_skill_dir.resolve():
            print(f"Source and target are the same: {source_path}")
            return True

        # Create target directory structure
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)

        # Backup existing if needed
        if not dry_run and target_skill_dir.exists():
            backup_path = create_backup(target_skill_dir, self.backup_dir)
            if backup_path and not is_symlink(target_skill_dir):
                # Only backup real directories
                pass

        # For independent git repos, prefer symlink to avoid copy permission issues
        if is_git_repo(source_path):
            if create_symlink(source_path, target_skill_dir):
                print(f"  Linked (git repo): {target_skill_dir} -> {source_path}")
                self.results["symlinks_created"].append(str(target_skill_dir))
                return True

        if dry_run:
            print(f"  [DRY-RUN] Would copy: {source_path} -> {target_skill_dir}")
            if remove_paths and create_symlinks:
                print(f"  [DRY-RUN] Would handle {len(remove_paths)} duplicate(s) for symlinks")
            return True

        # Copy the skill
        success = copy_skill(source_path, target_skill_dir, preserve_git=True)
        if not success:
            return False

        self.results["collected"].append(skill_name)

        # Handle symlinks for removed paths
        if create_symlinks:
            for remove_path in remove_paths:
                remove_expanded = expand_path(remove_path)
                if not remove_expanded.exists():
                    continue

                # If the removed path is a symlink, just remove it
                if is_symlink(remove_expanded):
                    if remove_symlink(remove_expanded):
                        self.results["symlinks_removed"].append(str(remove_expanded))
                else:
                    # It's a real directory, convert to symlink
                    # First backup
                    backup_path = create_backup(remove_expanded, self.backup_dir)

                    # Remove original
                    if remove_expanded.is_dir():
                        shutil.rmtree(remove_expanded)
                    else:
                        remove_expanded.unlink()

                    # Create symlink
                    if create_symlink(target_skill_dir, remove_expanded):
                        self.results["symlinks_created"].append(str(remove_expanded))

        return True

    def collect_all(
        self, target_dir: Path, skills: List[str] = None, create_symlinks: bool = True, dry_run: bool = False
    ) -> dict:
        """Collect all skills or specified skills to target directory."""
        target_dir = expand_path(str(target_dir))

        if skills:
            skill_names = skills
        else:
            # Collect all skills from index
            skill_names = list(self.index["skills"].keys())

        print(f"\nCollecting {len(skill_names)} skills to: {target_dir}")
        print("=" * 60)

        for skill_name in skill_names:
            print(f"\nProcessing: {skill_name}")
            self.collect_skill(skill_name, target_dir, create_symlinks, dry_run=dry_run)

        return self.results

    def create_single_symlink(
        self, skill_name: str, link_path: Path, target_path: Path = None
    ) -> bool:
        """Create a symlink for a single skill."""
        skill = self.index["skills"].get(skill_name)
        if not skill:
            print(f"Skill '{skill_name}' not found in index")
            return False

        if target_path is None:
            # Use the real location as target
            for loc in skill["locations"]:
                if not loc["is_symlink"]:
                    target_path = expand_path(loc["path"])
                    break

        if not target_path:
            print(f"No target path found for skill '{skill_name}'")
            return False

        target_path = expand_path(str(target_path))
        if is_symlink(target_path):
            target_path = resolve_symlink_target(target_path)

        return create_symlink(target_path, link_path)


def main():
    parser = argparse.ArgumentParser(description="Collect skills and create symlinks")
    parser.add_argument(
        "--index", "-i", type=str, required=True, help="Path to index.json"
    )
    parser.add_argument(
        "--decisions", "-d", type=str, help="Path to decisions.json from deduplicate.py"
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        required=True,
        help="Target directory for collected skills",
    )
    parser.add_argument(
        "--skills",
        "-s",
        type=str,
        nargs="+",
        help="Specific skills to collect (default: all)",
    )
    parser.add_argument(
        "--no-symlink",
        action="store_true",
        help="Do not create symlinks for removed duplicates",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"Error: Index file not found: {index_path}")
        return 1

    decisions_path = Path(args.decisions) if args.decisions else None

    collector = SkillCollector(index_path, decisions_path)

    # Collect (dry_run flag controls per-skill output, argparse dry-run is handled separately)
    results = collector.collect_all(
        target_dir=args.target, skills=args.skills, create_symlinks=not args.no_symlink, dry_run=args.dry_run
    )

    if args.dry_run:
        print("\nDry run mode - no changes were actually made")
        print(f"Target directory: {args.target}")
        print(f"Skills to process: {args.skills or 'all'}")
        return 0

    # Print summary
    print("\n" + "=" * 60)
    print("Collection Summary")
    print("=" * 60)
    print(f"Collected: {len(results['collected'])}")
    print(f"Symlinks created: {len(results['symlinks_created'])}")
    print(f"Symlinks removed: {len(results['symlinks_removed'])}")
    print(f"Errors: {len(results['errors'])}")

    if results["collected"]:
        print(f"\nCollected skills:")
        for name in results["collected"]:
            print(f"  + {name}")

    if results["symlinks_created"]:
        print(f"\nCreated symlinks:")
        for path in results["symlinks_created"]:
            print(f"  → {path}")

    if results["symlinks_removed"]:
        print(f"\nRemoved symlinks:")
        for path in results["symlinks_removed"]:
            print(f"  - {path}")

    if results["errors"]:
        print(f"\nErrors:")
        for err in results["errors"]:
            print(f"  ! {err['skill']}: {err['error']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
