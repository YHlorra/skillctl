#!/usr/bin/env python3
"""
Skill Manager - Adopt Skills Module

Discover unmanaged skills in a source directory (default ~/.claude/skills/),
copy them into the library, and replace the source with a junction (Windows)
or symlink (Unix) pointing to the canonical library location.

Usage:
    python adopt_skills.py --source <dir> --library <dir> [--dry-run]
    python adopt_skills.py --yes --backup <dir> --rebuild-index

Flags:
    --dry-run         Preview only; do not move/copy/link anything
    --yes             Skip interactive confirmation
    --backup DIR      Backup original source to this dir before adoption
    --rebuild-index   Run scan to refresh index.json after adoption
    --source PATH     Source directory to scan (default: ~/.claude/skills/)
    --library PATH    Target library root (default: SKILL_LIBRARY_PATH or user.json)
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from _lib.gates import run_gates, format_report
from _lib.tty import should_prompt_user, prompt_user_confirm


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def resolve_library_path() -> Path:
    """
    Resolve the canonical library path.
    Resolution chain (first match wins):
      1. SKILL_LIBRARY_PATH env var
      2. user.json library_path field
    Exits with clear message if neither is set.
    """
    env_path = os.environ.get("SKILL_LIBRARY_PATH")
    if env_path:
        path = expand_path(env_path)
        if path.exists() or path.parent.exists():
            return path

    try:
        from user_config import resolve_library_path as _resolve
        resolved = _resolve()
        if resolved is not None:
            if resolved.exists() or resolved.parent.exists():
                return resolved
    except ImportError:
        pass

    sys.exit(
        "ERROR: Cannot determine library path.\n"
        "  Set one of:\n"
        "    - env var SKILL_LIBRARY_PATH\n"
        "    - user.json field 'library_path' (see references/user-config.md)\n"
        "  See references/user-config.md for details."
    )


def resolve_source_path(source_arg: str | None) -> Path:
    """Resolve the source directory to scan for unmanaged skills."""
    if source_arg:
        path = expand_path(source_arg)
        if not path.exists():
            sys.exit(f"Error: source directory does not exist: {path}")
        return path
    return expand_path("~/.claude/skills")


def create_junction(link_path: Path, target_path: Path) -> tuple[bool, str]:
    """
    Create a junction (Windows) or symlink (Unix) at link_path pointing to target_path.
    This is the inverse of collect_and_link.py's direction.
    Returns (True, msg) on success, (False, msg) on failure.
    """
    try:
        # Remove existing link/path if present
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_symlink():
                link_path.unlink()
            elif link_path.is_dir():
                return False, f"link path is a real directory, not a symlink: {link_path}"

        if sys.platform == "win32":
            # Windows: try symlink first, fallback to junction via mklink /J
            try:
                os.symlink(str(target_path), str(link_path), target_is_directory=True)
                print(f"  Created symlink: {link_path} -> {target_path}")
            except OSError:
                # Fallback: junction on Windows
                subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link_path), str(target_path)],
                    check=True,
                    capture_output=True,
                )
                print(f"  Created junction: {link_path} -> {target_path}")
        else:
            os.symlink(str(target_path), str(link_path))
            print(f"  Created symlink: {link_path} -> {target_path}")
        return True, ""
    except Exception as e:
        print(f"  Error creating junction/symlink: {e}")
        return False, str(e)


def is_junction(path: Path) -> bool:
    """Check if path is a junction point (Windows)."""
    if sys.platform != "win32":
        return path.is_symlink()
    try:
        return path.is_symlink()
    except OSError:
        return False


def get_managed_skill_names(library_path: Path) -> set[str]:
    """Read index.json and return set of already-managed skill names."""
    idx_file = library_path / "index.json"
    if not idx_file.exists():
        return set()
    try:
        data = json.loads(idx_file.read_text(encoding="utf-8"))
        skills = data.get("skills", {})
        return set(skills.keys())
    except (json.JSONDecodeError, OSError):
        return set()


def copy_skill_files(src_skill_dir: Path, dst_skill_dir: Path) -> bool:
    """
    Copy the entire skill directory from src to dst using shutil.copytree.
    Mirrors the pattern in collect_and_link.py:copy_skill().
    Returns True on success.
    """
    try:
        # Ensure parent dir exists (shutil.copytree creates dst itself)
        dst_skill_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_skill_dir, dst_skill_dir, symlinks=False, dirs_exist_ok=False)
        return True
    except Exception as e:
        print(f"  Error copying skill: {e}")
        return False


def backup_source(src_skill_dir: Path, backup_root: Path, skill_name: str) -> Path | None:
    """Move src_skill_dir to backup_root/<skill_name>_timestamp/."""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = backup_root / f"{skill_name}_{ts}"
        backup_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_skill_dir, backup_dir)
        return backup_dir
    except Exception as e:
        print(f"  Warning: backup failed: {e}")
        return None


def adopt_skill(
    src_skill_dir: Path,
    library_path: Path,
    dry_run: bool,
    backup_root: Path | None,
    confirmed: bool,
) -> tuple[str, str]:
    """
    Adopt a single skill: copy to library, optionally backup source, create junction.
    Returns (status, msg) where status is 'adopted' | 'skipped' | 'error'.
    """
    skill_name = src_skill_dir.name
    dst_skill_dir = library_path / skill_name

    if dry_run:
        print(f"  [adopt] WOULD copy {src_skill_dir} -> {dst_skill_dir}")
        print(f"  [adopt] WOULD junction {src_skill_dir} -> {dst_skill_dir}")
        return "adopted", "dry-run"

    # Check if already exists in library
    if dst_skill_dir.exists():
        return "skipped", f"target already exists: {dst_skill_dir}"

    # Backup source if requested
    if backup_root:
        backup_dir = backup_source(src_skill_dir, backup_root, skill_name)
        if backup_dir:
            print(f"  Backed up to: {backup_dir}")

    # Copy skill files
    if not copy_skill_files(src_skill_dir, dst_skill_dir):
        return "error", "copy failed"

    # Verify copy
    if not (dst_skill_dir / "SKILL.md").exists():
        return "error", "copy verification failed: SKILL.md not found in destination"

    # Remove original source (now safely copied)
    try:
        shutil.rmtree(src_skill_dir)
    except Exception as e:
        print(f"  Warning: could not remove original source: {e}")

    # Create junction at source pointing to library location
    ok, err = create_junction(src_skill_dir, dst_skill_dir)
    if not ok:
        return "error", f"junction creation failed: {err}"

    return "adopted", "ok"


def main():
    parser = argparse.ArgumentParser(
        description="Adopt unmanaged skills from a source directory into the library."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview only; do not move/copy/link anything"
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip interactive confirmation"
    )
    parser.add_argument(
        "--backup", type=str,
        help="Backup original source to this directory before adoption"
    )
    parser.add_argument(
        "--rebuild-index", action="store_true",
        help="Run scan to refresh index.json after adoption"
    )
    parser.add_argument(
        "--source", type=str,
        help="Source directory to scan (default: ~/.claude/skills/)"
    )
    parser.add_argument(
        "--library", type=str,
        help="Target library root (default: SKILL_LIBRARY_PATH or user.json)"
    )
    parser.add_argument(
        "--gate-mode", type=str, choices=["enforce", "skip"], default="enforce",
        help="Gate validation before adoption: enforce (fail if gates don't pass) or skip (skip gates)"
    )
    parser.add_argument(
        "--no-gate", action="store_true", default=False,
        help="Skip gate validation (equivalent to --gate-mode skip)"
    )
    parser.add_argument(
        "--non-interactive", action="store_true", default=False,
        help="Auto-confirm adoption without prompting"
    )

    args = parser.parse_args()

    # Resolve paths
    source_path = resolve_source_path(args.source)

    # Override library resolution if --library is given
    if args.library:
        library_path = expand_path(args.library)
    else:
        library_path = resolve_library_path()

    print(f"[adopt] Source:  {source_path}")
    print(f"[adopt] Library: {library_path}")
    print(f"[adopt] Mode:    {'DRY-RUN' if args.dry_run else 'LIVE'}")
    if args.backup:
        print(f"[adopt] Backup:  {args.backup}")
    print()

    # Read managed skills from index
    managed = get_managed_skill_names(library_path)
    print(f"[adopt] Already managed in library: {len(managed)} skill(s)")

    # Find skills in source directory
    if not source_path.exists():
        print(f"Error: source directory does not exist: {source_path}")
        return 1

    src_skills = []
    for item in source_path.iterdir():
        if not item.is_dir():
            continue
        if is_junction(item):
            continue  # Skip existing junctions
        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue
        src_skills.append(item)

    if not src_skills:
        print("[adopt] No adoptable skills found in source directory.")
        return 0

    print(f"[adopt] Found {len(src_skills)} skill(s) in source directory")

    # Filter out already-managed skills
    to_adopt = [s for s in src_skills if s.name not in managed]
    already_managed = [s for s in src_skills if s.name in managed]
    if already_managed:
        print(f"[adopt] Skipping {len(already_managed)} already-managed skill(s)")

    if not to_adopt:
        print("[adopt] Nothing to adopt.")
        return 0

    # Process each skill
    backup_root = Path(args.backup) if args.backup else None
    adopted = 0
    skipped = 0
    gated_out = 0
    errors = 0
    gate_mode = "skip" if args.no_gate else args.gate_mode
    non_interactive = args.non_interactive or args.yes  # --yes also means non-interactive

    for skill_dir in to_adopt:
        print(f"\n[adopt] Processing: {skill_dir.name}")

        # Gate evaluation (runs in both dry-run and live mode)
        if gate_mode != "skip":
            report = run_gates(skill_dir)
            print(format_report(report), end="")
            if not report.gates_passed:
                print(f"  Gate failure. Use --no-gate to override (NOT recommended).")
                gated_out += 1
                if args.dry_run:
                    print(f"  [adopt] WOULD NOT adopt {skill_dir.name} (gate failed).")
                else:
                    print(f"  Skip {skill_dir.name}.")
                    skipped += 1
                continue

        # User confirmation (skip in dry-run)
        if args.dry_run:
            confirm = True
        elif should_prompt_user(non_interactive):
            confirm = prompt_user_confirm(f"Adopt this skill?")
        else:
            confirm = True  # auto-confirm in non-interactive

        if not confirm:
            print(f"  Skipped {skill_dir.name}.")
            skipped += 1
            continue

        status, msg = adopt_skill(
            skill_dir,
            library_path,
            dry_run=args.dry_run,
            backup_root=backup_root,
            confirmed=True,
        )
        if status == "adopted":
            adopted += 1
        elif status == "skipped":
            skipped += 1
            print(f"  Skipped: {msg}")
        else:
            errors += 1
            print(f"  Error: {msg}")

    # Rebuild index if requested
    if args.rebuild_index and adopted > 0 and not args.dry_run:
        print(f"\n[adopt] Rebuilding index...")
        scan_script = Path(__file__).parent / "scan_and_index.py"
        # Scan the library directory (not source), using the canonical scan path
        result = subprocess.run(
            [sys.executable, str(scan_script), "--library", str(library_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            print(f"  Warning: index rebuild returned exit code {result.returncode}")
            if result.stdout:
                print(f"  stdout: {result.stdout[:200]}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:200]}")

    # Summary
    print(f"\n=== Adoption Summary ===")
    print(f"  Considered: {len(to_adopt)}")
    print(f"  Adopted:    {adopted}")
    if gated_out > 0:
        print(f"  Gated out:  {gated_out}")
    print(f"  Skipped:    {skipped}")
    print(f"  Errors:     {errors}")

    # Exit code: 4 if all candidates failed gates; 0 if at least one succeeded; 1 on error
    # Dry-run always exits 0 (informational only, never a real failure)
    if args.dry_run:
        return 0
    if errors > 0:
        return 1
    if len(to_adopt) > 0 and adopted == 0 and gated_out == len(to_adopt):
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
