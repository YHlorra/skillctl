"""
Migrate all skills from nested Git repos to main library <library>

For each nested repo:
1. Copy all skills from nested_repo/skills/ to <library>/
2. Keep the nested repo as a git repo for future updates (git pull to update)
3. Optionally remove the skills/ subdir after migration

Usage:
    python migrate_nested_to_main.py --dry-run
    python migrate_nested_to_main.py --execute
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from _lib.gates import run_gates, format_report
from _lib.tty import should_prompt_user, prompt_user_confirm

from user_config import resolve_library_path
_BASE_DIR_RESOLVED = resolve_library_path()
if _BASE_DIR_RESOLVED is None:
    raise SystemExit(
        "ERROR: SKILL_LIBRARY_PATH not set and user.json 'library_path' missing. "
        "See references/user-config.md."
    )
BASE_DIR = _BASE_DIR_RESOLVED
INDEX_FILE = BASE_DIR / "skillctl" / "index.json"
BACKUP_DIR = BASE_DIR / ".backup_nested_migration"


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def load_index() -> dict:
    """Load index.json."""
    if not INDEX_FILE.exists():
        return {}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index: dict):
    """Save index.json."""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def create_backup(path: Path) -> Path:
    """Create backup of a directory."""
    if not path.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{path.name}_{timestamp}"
    backup_path = BACKUP_DIR / backup_name

    try:
        shutil.copytree(path, backup_path, symlinks=False, dirs_exist_ok=False)
        print(f"  Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"  Warning: Backup failed: {e}")
        return None


class NestedRepoMigrator:
    """Migrate skills from nested Git repos to main library."""

    def __init__(self, dry_run: bool = True, gate_mode: str = "enforce", non_interactive: bool = False):
        self.dry_run = dry_run
        self.gate_mode = gate_mode
        self.non_interactive = non_interactive
        self.index = load_index()
        self.nested_repos = self.index.get("nested_repos", [])
        self.migrated = []
        self.skipped = []
        self.gated_out = []
        self.errors = []

    def migrate_all(self):
        """Migrate skills from all nested repos."""
        print(f"\n{'=' * 70}")
        print(f" Migrating Nested Repos to Main Library")
        print(f"{'=' * 70}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'EXECUTE'}")
        print(f"Main library: {BASE_DIR}")
        print(f"Nested repos: {len(self.nested_repos)}")
        print()

        for repo in self.nested_repos:
            repo_path = Path(repo["repo_path"])
            skills_path = Path(repo["skills_path"])
            git_url = repo.get("git_url", "N/A")

            print(f"{'=' * 70}")
            print(f"Repository: {repo_path.name}")
            print(f"  Git: {git_url}")
            print(f"  Skills path: {skills_path}")

            if not skills_path.exists():
                print(f"  [SKIP] Skills path not found")
                self.skipped.append({"repo": repo_path.name, "reason": "path not found"})
                continue

            # Count skills
            skills = [
                p for p in skills_path.iterdir()
                if p.is_dir() and (p / "SKILL.md").exists()
            ]
            print(f"  Skills to migrate: {len(skills)}")

            if self.dry_run:
                for skill in skills:
                    # Gate runs even in dry-run (for visibility)
                    if self.gate_mode != "skip":
                        report = run_gates(skill)
                        print(format_report(report), end="")
                        if not report.gates_passed:
                            print(f"    Gate failure. Use --no-gate to override.")
                            print(f"    Skip {skill.name}.")
                            self.gated_out.append({"skill": skill.name, "repo": repo_path.name})
                            continue
                    skill_path = BASE_DIR / skill.name
                    if skill_path.exists():
                        print(f"    [EXISTS] {skill.name}")
                    else:
                        print(f"    [WILL COPY] {skill.name}")
                continue

            # Execute migration
            for skill in skills:
                # Gate evaluation
                if self.gate_mode != "skip":
                    report = run_gates(skill)
                    print(format_report(report), end="")
                    if not report.gates_passed:
                        print(f"    Gate failure. Use --no-gate to override.")
                        print(f"    Skip {skill.name}.")
                        self.gated_out.append({"skill": skill.name, "repo": repo_path.name})
                        continue

                # User confirmation
                if should_prompt_user(self.non_interactive):
                    if not prompt_user_confirm(f"Migrate {skill.name}?"):
                        print(f"    Skipped {skill.name}.")
                        self.skipped.append({"skill": skill.name, "repo": repo_path.name, "reason": "user declined"})
                        continue

                target_path = BASE_DIR / skill.name
                skill_backup = None

                # Backup if exists
                if target_path.exists():
                    skill_backup = create_backup(target_path)
                    try:
                        shutil.rmtree(target_path)
                    except Exception as e:
                        self.errors.append({
                            "skill": skill.name,
                            "error": f"Failed to remove existing: {e}"
                        })
                        continue

                # Copy skill
                try:
                    shutil.copytree(skill, target_path, symlinks=False, dirs_exist_ok=False)
                    self.migrated.append({
                        "skill": skill.name,
                        "source": str(skill),
                        "target": str(target_path),
                        "backup": str(skill_backup) if skill_backup else None
                    })
                    print(f"    [MIGRATED] {skill.name}")
                except Exception as e:
                    self.errors.append({
                        "skill": skill.name,
                        "error": str(e)
                    })
                    # Restore backup if exists
                    if skill_backup and skill_backup.exists():
                        try:
                            shutil.rmtree(target_path)
                            shutil.copytree(skill_backup, target_path)
                            print(f"    [RESTORED FROM BACKUP] {skill.name}")
                        except:
                            pass
                    print(f"    [ERROR] {skill.name}: {e}")

        return self.get_results()

    def get_results(self) -> dict:
        """Get migration results."""
        return {
            "migrated": self.migrated,
            "skipped": self.skipped,
            "gated_out": self.gated_out,
            "errors": self.errors,
            "total_migrated": len(self.migrated),
            "total_skipped": len(self.skipped),
            "total_gated_out": len(self.gated_out),
            "total_errors": len(self.errors),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate skills from nested Git repos to main library"
    )
    parser.add_argument(
        "--execute", "-e", action="store_true",
        help="Execute migration (default is dry-run)"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--gate-mode", type=str, choices=["enforce", "skip"], default="enforce",
        help="Gate validation before migration: enforce (fail if gates don't pass) or skip (skip gates)"
    )
    parser.add_argument(
        "--no-gate", action="store_true", default=False,
        help="Skip gate validation (equivalent to --gate-mode skip)"
    )
    parser.add_argument(
        "--non-interactive", action="store_true", default=False,
        help="Auto-confirm migration without prompting"
    )

    args = parser.parse_args()

    # Default to dry-run if neither execute nor dry-run specified
    dry_run = not args.execute

    migrator = NestedRepoMigrator(
        dry_run=dry_run,
        gate_mode="skip" if args.no_gate else args.gate_mode,
        non_interactive=args.non_interactive,
    )
    results = migrator.migrate_all()

    # Print summary
    print(f"\n{'=' * 70}")
    print(f" Migration Summary")
    print(f"{'=' * 70}")
    print(f"  Migrated:   {results['total_migrated']}")
    if results.get("total_gated_out"):
        print(f"  Gated out: {results['total_gated_out']}")
    print(f"  Skipped:   {results['total_skipped']}")
    print(f"  Errors:    {results['total_errors']}")

    if results["migrated"]:
        print(f"\nMigrated skills:")
        for item in results["migrated"]:
            print(f"  + {item['skill']}")

    if results["errors"]:
        print(f"\nErrors:")
        for err in results["errors"]:
            print(f"  ! {err['skill']}: {err['error']}")

    if dry_run:
        print(f"\n[DRY RUN] Use --execute to actually migrate.")

    # Exit code: 4 if all candidates gated out; 1 on errors; 0 otherwise
    # Dry-run always exits 0 (informational only, never a real failure)
    if dry_run:
        return 0
    candidates = results["total_migrated"] + results["total_gated_out"]
    if results["total_errors"] > 0:
        return 1
    if candidates > 0 and results["total_migrated"] == 0 and results["total_gated_out"] > 0:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
