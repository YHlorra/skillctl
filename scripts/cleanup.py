def scan_cleanup(scan_path: Path) -> dict:
    """Scan for orphan symlinks, empty dirs, and broken backups."""
    orphan_symlinks = []
    empty_dirs = []
    broken_backups = []
    _visited_paths = set()
    # ... body of scan() inlined here


#!/usr/bin/env python3
"""
Skill Manager - Cleanup Module

清理功能：
1. 清理孤儿 symlink（指向目标已不存在的 symlink）
2. 清理空目录
3. 清理孤儿备份目录（指向已不存在的 skill）
4. 生成清理报告

Usage:
    python cleanup.py --dry-run                    # 预览模式
    python cleanup.py --scan-path <library_path>   # 扫描路径
    python cleanup.py --remove                      # 实际删除

Path resolution for --scan-path:
  1. --scan-path argument if provided
  2. SKILL_LIBRARY_PATH env var
  3. user.json library_path field
  4. ERROR — refuse to run with no library configured
    python cleanup.py --json                         # JSON 输出
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from _lib.paths import expand_path, is_symlink, resolve_symlink_target
from _lib.paths import expand_path, is_symlink, resolve_symlink_target

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def is_empty_dir(path: Path) -> bool:
    """Check if directory is truly empty."""
    if not path.is_dir():
        return False
    try:
        return len(os.listdir(path)) == 0
    except OSError:
        return False

def is_orphan_symlink(path: Path) -> Tuple[bool, str]:
    """
    Check if symlink is orphan (target no longer exists).
    Returns (is_orphan, reason).
    """
    if not is_symlink(path):
        return False, ""

    try:
        target = resolve_symlink_target(path)
        if not target.exists():
            return True, f"target not found: {target}"
        return False, ""
    except Exception as e:
        return True, f"resolve error: {e}"

def is_broken_backup_dir(path: Path) -> Tuple[bool, str]:
    """
    Check if directory looks like a broken backup/backup_cleanup dir.
    These often contain partial skill copies that are no longer needed.
    A backup dir is broken only if it has subdirectories but NONE of them
    contain any valid skill content (SKILL.md or .git).
    Returns (is_broken, reason).
    """
    name = path.name

    # Check if it's a backup directory pattern
    is_backup = name.startswith(".backup") or name.startswith(".backup_cleanup")

    if not is_backup:
        return False, ""

    # Check if it contains any valid skill structure
    # A valid backup might have SKILL.md or .git or other valid content
    has_skill_md = (path / "SKILL.md").exists()
    has_git = (path / ".git").exists() or (path / ".git").is_file()

    if has_skill_md or has_git:
        return False, ""

    # Check if any subdirectory has valid skill content
    for subdir in path.iterdir():
        if subdir.is_dir():
            if (subdir / "SKILL.md").exists() or (subdir / ".git").exists():
                return False, ""
            # Recursively check nested backup dirs
            nested_backup, _ = is_broken_backup_dir(subdir)
            if not nested_backup:
                return False, ""

    # It's a backup dir without any valid skill content anywhere
    return True, "backup dir without valid skill content"

def scan_cleanup(scan_path: Path):
    """Scan scan_path for cleanup candidates."""
    if not scan_path.exists():
        print(f"Error: Path does not exist: {scan_path}")
        return [], [], []

    print(f"Scanning: {scan_path}")

    orphan_symlinks = []
    empty_dirs = []
    broken_backups = []
    _visited_paths = set()

    def _check_item(path: Path):
        if is_symlink(path):
            is_orphan, reason = is_orphan_symlink(path)
            if is_orphan:
                orphan_symlinks.append({
                    "path": str(path),
                    "name": path.name,
                    "reason": reason,
                })
                return

        if path.is_dir() and is_empty_dir(path):
            empty_dirs.append({
                "path": str(path),
                "name": path.name,
            })
            return

        is_broken, reason = is_broken_backup_dir(path)
        if is_broken and path not in [Path(b["path"]) for b in broken_backups]:
            broken_backups.append({
                "path": str(path),
                "name": path.name,
                "reason": reason,
            })

    def _scan_nested(parent: Path):
        try:
            for item in parent.iterdir():
                if not item.is_dir():
                    continue
                real_path = str(item.resolve()) if is_symlink(item) else str(item)
                if real_path in _visited_paths:
                    continue
                _visited_paths.add(real_path)
                if item.name in (".git", "node_modules", "__pycache__", ".venv", "venv"):
                    continue
                if item.name.startswith(".backup"):
                    _check_item(item)
                    continue
                _check_item(item)
                if item.is_dir() and not is_symlink(item):
                    _scan_nested(item)
        except PermissionError:
            pass

    for item in scan_path.iterdir():
        if not item.is_dir():
            continue
        _check_item(item)

    _scan_nested(scan_path)

    return orphan_symlinks, empty_dirs, broken_backups


def get_cleanup_summary(orphan_symlinks, empty_dirs, broken_backups) -> dict:
    """Get cleanup summary."""
    return {
        "scan_path": str(scan_path),
        "scan_time": datetime.now().isoformat(),
        "orphan_symlinks": len(orphan_symlinks),
        "empty_dirs": len(empty_dirs),
        "broken_backups": len(broken_backups),
        "total_items": len(orphan_symlinks) + len(empty_dirs) + len(broken_backups),
    }


def remove_cleanup_items(orphan_symlinks, empty_dirs, broken_backups, dry_run: bool = True) -> dict:
    results = {
        "symlinks_removed": [],
        "dirs_removed": [],
        "backups_removed": [],
        "errors": [],
    }

    if dry_run:
        print("\n[DRY RUN] Would remove:")

    for item in orphan_symlinks:
        path = Path(item["path"])
        if dry_run:
            print(f"  [symlink] {path}")
        else:
            try:
                if is_symlink(path):
                    path.unlink()
                    results["symlinks_removed"].append(item["path"])
                    print(f"  Removed symlink: {path}")
            except Exception as e:
                results["errors"].append({"path": item["path"], "error": str(e)})

    for item in empty_dirs:
        path = Path(item["path"])
        if dry_run:
            print(f"  [empty dir] {path}")
        else:
            try:
                os.rmdir(path)
                results["dirs_removed"].append(item["path"])
                print(f"  Removed empty dir: {path}")
            except Exception as e:
                results["errors"].append({"path": item["path"], "error": str(e)})

    for item in broken_backups:
        path = Path(item["path"])
        if dry_run:
            print(f"  [backup] {path}")
        else:
            try:
                shutil.rmtree(path)
                results["backups_removed"].append(item["path"])
                print(f"  Removed backup: {path}")
            except Exception as e:
                results["errors"].append({"path": item["path"], "error": str(e)})

    return results



def print_cleanup_report(orphan_symlinks, empty_dirs, broken_backups, results: dict = None):
    """Print cleanup report."""
    summary = get_cleanup_summary(orphan_symlinks, empty_dirs, broken_backups)

    print(f"\n{'=' * 70}")
    print(f" Cleanup Report")
    print(f"{'=' * 70}")
    print(f"Scan path: {summary['scan_path']}")
    print(f"Scan time: {summary['scan_time']}")
    print(f"\nFound cleanup candidates:")
    print(f"  Orphan symlinks: {summary['orphan_symlinks']}")
    print(f"  Empty directories: {summary['empty_dirs']}")
    print(f"  Broken backups: {summary['broken_backups']}")
    print(f"  Total: {summary['total_items']}")

    if orphan_symlinks:
        print(f"\n{'=' * 70}")
        print(f" Orphan Symlinks ({len(orphan_symlinks)})")
        print(f"{'=' * 70}")
        for item in orphan_symlinks:
            print(f"  • {item['path']}")
            print(f"    Reason: {item['reason']}")

    if empty_dirs:
        print(f"\n{'=' * 70}")
        print(f" Empty Directories ({len(empty_dirs)})")
        print(f"{'=' * 70}")
        for item in empty_dirs:
            print(f"  • {item['path']}")

    if broken_backups:
        print(f"\n{'=' * 70}")
        print(f" Broken Backup Directories ({len(broken_backups)})")
        print(f"{'=' * 70}")
        for item in broken_backups:
            print(f"  • {item['path']}")
            print(f"    Reason: {item['reason']}")

    if results:
        print(f"\n{'=' * 70}")
        print(f" Removal Results")
        print(f"{'=' * 70}")
        print(f"  Symlinks removed: {len(results['symlinks_removed'])}")
        print(f"  Directories removed: {len(results['dirs_removed'])}")
        print(f"  Backups removed: {len(results['backups_removed'])}")
        if results["errors"]:
            print(f"  Errors: {len(results['errors'])}")
            for err in results["errors"]:
                print(f"    ! {err['path']}: {err['error']}")

def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - Cleanup orphaned symlinks, empty directories, and broken backups"
    )
    parser.add_argument(
        "--scan-path", "-p", type=str,
        help="Path to scan for cleanup candidates "
             "(falls back to SKILL_LIBRARY_PATH env, then user.json library_path)"
    )
    parser.add_argument(
        "--remove", "-r", action="store_true",
        help="Actually remove items (default is dry-run)"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be done without making changes (default)"
    )
    parser.add_argument(
        "--json", "-j", action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--symlinks-only", "-s", action="store_true",
        help="Only clean orphan symlinks"
    )
    parser.add_argument(
        "--empty-only", "-e", action="store_true",
        help="Only clean empty directories"
    )
    parser.add_argument(
        "--backup-only", "-b", action="store_true",
        help="Only clean broken backup directories"
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="Force removal without confirmation prompt"
    )

    args = parser.parse_args()

    # Determine scan path
    if args.scan_path:
        scan_path = expand_path(args.scan_path)
    else:
        # Resolve from env > user.json > error. Never fall back to a
        # hard-coded path — every operator's library is different.
        from user_config import resolve_library_path
        resolved = resolve_library_path()
        if resolved is None:
            print(
                "ERROR: --scan-path not given and SKILL_LIBRARY_PATH/user.json "
                "not configured. See references/user-config.md.",
                file=sys.stderr,
            )
            return 2
        scan_path = resolved

    # Scan
    scanner = CleanupScanner(scan_path)
    scan(scan_path)

    # Filter if specific cleanup type requested
    if args.symlinks_only:
        empty_dirs = []
        broken_backups = []
    if args.empty_only:
        orphan_symlinks = []
        broken_backups = []
    if args.backup_only:
        orphan_symlinks = []
        empty_dirs = []

    # Output
    if args.json:
        output = {
            "summary": get_summary(orphan_symlinks, empty_dirs, broken_backups),
            "orphan_symlinks": orphan_symlinks,
            "empty_dirs": empty_dirs,
            "broken_backups": broken_backups,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    # Print report
    print_cleanup_report(scanner)

    # Remove if requested
    results = None
    if args.remove and not args.dry_run:
        if get_summary(orphan_symlinks, empty_dirs, broken_backups)["total_items"] > 0:
            print(f"\n{'=' * 70}")
            if args.force:
                confirm = "y"
            else:
                confirm = input("Confirm removal? [y/N]: ").strip().lower()
            if confirm == "y":
                results = remove_all(dry_run=False)
            else:
                print("Cancelled.")
        else:
            print("\nNo items to remove.")
    elif not args.remove:
        print(f"\n{'=' * 70}")
        print("Dry run complete. Use --remove to actually delete.")

    return 0

if __name__ == "__main__":
    sys.exit(main())
