"""Canonical path utilities shared across L2 scripts."""
from __future__ import annotations

import os
from pathlib import Path


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def is_symlink(path: Path) -> bool:
    r"""Check if path is a symlink, junction, or under a symlinked ancestor."""
    try:
        if path.is_symlink():
            return True
        current = path.parent
        while current != current.parent:
            try:
                if current.is_symlink():
                    return True
                if os.name == "nt":
                    try:
                        resolved = current.resolve()
                        if resolved != current and current.is_dir():
                            return True
                    except (OSError, RuntimeError):
                        pass
            except OSError:
                break
            current = current.parent
        if os.name == "nt":
            try:
                resolved = path.resolve()
                if resolved != path and path.is_dir():
                    return True
            except (OSError, RuntimeError):
                pass
        return False
    except OSError:
        return False


def resolve_symlink_target(path: Path) -> Path:
    """Resolve symlink to real path."""
    try:
        return path.resolve()
    except OSError:
        return path


def is_git_repo(path: Path) -> bool:
    """Check if a directory is a git repository."""
    return (path / ".git").exists()
