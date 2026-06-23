#!/usr/bin/env python3
"""
skillctl user_config module — per-user personalization (NEVER committed).

This file provides the resolution layer for per-user settings that are
specific to one machine or one operator. The corresponding data file is
``user.json`` and is intentionally gitignored — see ``references/user-config.md``
for the schema and rationale.

Resolution order for any setting:

    1. ``SKILLCTL_USER_CONFIG`` env var (explicit override path to a JSON file)
    2. XDG-compliant ``user.json`` location:

       - Linux: ``$XDG_CONFIG_HOME/skillctl/user.json`` or
         ``~/.config/skillctl/user.json``
       - macOS: ``~/Library/Application Support/skillctl/user.json``
       - Windows: ``%APPDATA%\\skillctl\\user.json`` (resolves to
         ``C:\\Users\\<user>\\AppData\\Roaming\\skillctl\\user.json``)

    3. Empty dict — callers must apply their own built-in defaults.

Schema (all fields optional; missing keys are silently treated as unset):

    {
      "library_path": "C:/Users/me/skills",
      "scan_paths": [
        {"path": "~/.claude/skills", "scope": "global", "priority": "high"},
        {"path": "~/projects/foo/.claude/skills", "scope": "project", "priority": "medium"}
      ],
      "default_flags": {
        "update_timeout": 60
      }
    }

Usage:

    from user_config import load_user_config, get_library_path, get_scan_paths

    cfg = load_user_config()
    lib = get_library_path(cfg)   # returns Path or None
    paths = get_scan_paths(cfg)    # returns list[dict] or []
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


# Force UTF-8 for stdout on Windows (matches sibling modules)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


USER_CONFIG_FILENAME = "user.json"
USER_CONFIG_ENV_VAR = "SKILLCTL_USER_CONFIG"


def _user_config_path() -> Optional[Path]:
    """Resolve the user.json path. Returns None if not found / not set.

    Does NOT raise on missing file — callers fall back to defaults.
    """
    # 1. Explicit override
    explicit = os.environ.get(USER_CONFIG_ENV_VAR)
    if explicit:
        p = Path(os.path.expandvars(os.path.expanduser(explicit)))
        if p.is_file():
            return p
        # Explicit path set but file missing — don't fall through silently.
        # Caller should treat as "configured but unreadable".
        return None

    # 2. XDG-compliant search
    home = Path.home()

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = Path(appdata) / "skillctl" / USER_CONFIG_FILENAME
            if candidate.is_file():
                return candidate
        # Fallback: %USERPROFILE%\AppData\Roaming\skillctl\user.json
        userprofile = os.environ.get("USERPROFILE") or str(home)
        candidate = Path(userprofile) / "AppData" / "Roaming" / "skillctl" / USER_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        return None

    if sys.platform == "darwin":
        candidate = home / "Library" / "Application Support" / "skillctl" / USER_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        return None

    # Linux / *BSD / other Unix
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        candidate = Path(xdg) / "skillctl" / USER_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    candidate = home / ".config" / "skillctl" / USER_CONFIG_FILENAME
    if candidate.is_file():
        return candidate
    return None


def load_user_config() -> dict[str, Any]:
    """Read user.json. Returns empty dict if not configured.

    Never raises on missing file. Returns {} so callers can use
    ``cfg.get(key, default)`` uniformly.
    """
    path = _user_config_path()
    if path is None:
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def get_library_path(cfg: dict[str, Any]) -> Optional[Path]:
    """Return the configured library_path as a Path, or None if unset/invalid."""
    raw = cfg.get("library_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def get_scan_paths(cfg: dict[str, Any]) -> list[dict[str, str]]:
    """Return the configured scan_paths list. Each entry is a dict.

    Schema per entry: {"path": str, "scope": "global"|"local"|"project",
    "priority": "high"|"medium"|"low"}. Missing fields default sensibly.
    Returns [] if not configured or malformed.
    """
    raw = cfg.get("scan_paths")
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path")
        if not isinstance(p, str) or not p.strip():
            continue
        out.append(
            {
                "path": os.path.expandvars(os.path.expanduser(p)),
                "scope": entry.get("scope", "global"),
                "priority": entry.get("priority", "medium"),
            }
        )
    return out


def get_default_flag(cfg: dict[str, Any], flag: str, default: Any = None) -> Any:
    """Return a value from cfg.default_flags, or ``default`` if unset."""
    flags = cfg.get("default_flags")
    if not isinstance(flags, dict):
        return default
    return flags.get(flag, default)


def resolve_library_path(env_var: str = "SKILL_LIBRARY_PATH") -> Optional[Path]:
    """Resolve the canonical library path.

    Resolution chain (first match wins):

        1. ``env_var`` env var (defaults to ``SKILL_LIBRARY_PATH``)
        2. ``user.json`` ``library_path`` field (XDG-compliant location)

    Returns ``None`` if neither is configured. Callers should treat that
    as an error and emit a friendly message pointing at
    ``references/user-config.md``.

    This function does NOT raise. Scripts that need a hard requirement
    should ``sys.exit(1)`` with a clear message after calling this.
    """
    env_value = os.environ.get(env_var)
    if env_value:
        return Path(os.path.expandvars(os.path.expanduser(env_value)))
    cfg = load_user_config()
    return get_library_path(cfg)
