"""Unified backup layer for all write operations.

Single source of truth for backup paths, creation, and lifecycle.
All write commands (adopt, migrate, install --reinstall, link) MUST use
this module. The `delete` command is excluded by design — deletion is
irreversible and the user is expected to self-backup via `cp`/`mv` if
they want a safety net.

Layout
------
    <library>/.skillctl-backup/<YYYY-MM-DD>/<op-label>-<target>_<HHMMSS>/

Lifecycle
---------
    backup = create_backup(target, library, "migrate")   # snapshot target
    try:
        apply_change(target)
    except Exception as e:
        meta = keep_backup(backup, reason=str(e))        # retain on failure
        persist_last_tool_error(meta)
        raise
    else:
        commit_backup(backup)                            # auto-clean on success

This module never raises on commit/keep — failures during cleanup are
logged but never propagated (the protected operation already succeeded).
"""
from __future__ import annotations

import shutil
from datetime import datetime, date
from pathlib import Path

BACKUP_ROOT_NAME = ".skillctl-backup"


def get_backup_root(library_path: Path) -> Path:
    """Resolve <library>/.skillctl-backup/<YYYY-MM-DD>/ (creates date bucket)."""
    library_path = Path(library_path).resolve()
    root = library_path / BACKUP_ROOT_NAME / date.today().isoformat()
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_backup(
    source: Path,
    library_path: Path,
    op_label: str,
    *,
    ignore_git: bool = False,
) -> Path:
    """Snapshot `source` under the unified backup root.

    Args:
        source: Path to back up. Must exist. Directory or file.
        library_path: Library root; backup lives under it.
        op_label: Short tag like "migrate", "install-Waza", "adopt",
                  "link". Becomes part of the backup directory name.
        ignore_git: If True, exclude `.git/` from the copy. Required by
                    `install --reinstall` to avoid Windows file-lock on
                    `.git/pack/*` files.

    Returns:
        Absolute path to the created backup directory.

    Raises:
        FileNotFoundError: if `source` does not exist.
        OSError: on copy failure.
    """
    source = Path(source).resolve()
    library_path = Path(library_path).resolve()

    if not source.exists():
        raise FileNotFoundError(f"Cannot backup non-existent path: {source}")

    backup_root = get_backup_root(library_path)
    ts = datetime.now().strftime("%H%M%S")
    backup_name = f"{op_label}-{source.name}_{ts}"
    backup_path = backup_root / backup_name

    ignore = shutil.ignore_patterns(".git") if ignore_git else None

    if source.is_dir():
        shutil.copytree(
            source,
            backup_path,
            symlinks=False,
            dirs_exist_ok=False,
            ignore=ignore,
        )
    else:
        backup_path.mkdir(parents=True, exist_ok=False)
        shutil.copy2(source, backup_path / source.name)

    return backup_path


def commit_backup(backup_path: Path) -> bool:
    """Remove backup after the protected operation succeeded. Idempotent.

    Returns True if the backup directory existed and was removed;
    False if it was already gone (e.g. duplicate commit call).
    Never raises — the protected operation already succeeded.
    """
    backup_path = Path(backup_path)
    if not backup_path.exists():
        return False
    shutil.rmtree(backup_path)
    return True


def keep_backup(backup_path: Path, reason: str) -> dict:
    """Build a metadata record for a backup retained due to failure.

    No filesystem side effects — caller decides where to persist this
    (typically `last-tool-error.json`). The backup directory itself
    stays on disk until manually cleared or pruned.

    Args:
        backup_path: Path returned from create_backup().
        reason: Human-readable failure cause (typically str(exception)).

    Returns:
        Dict suitable for json.dump() into a state file.
    """
    return {
        "backup_path": str(backup_path),
        "reason": reason,
        "retained_at": datetime.now().isoformat(),
    }