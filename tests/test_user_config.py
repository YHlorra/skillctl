"""Tests for scripts/user_config.py resolution helpers."""
import json
import os
import sys
from pathlib import Path

import pytest


# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def clean_env(monkeypatch):
    """Remove user.json-related env vars so each test starts fresh."""
    for var in ("SKILLCTL_USER_CONFIG", "SKILL_LIBRARY_PATH", "XDG_CONFIG_HOME", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


@pytest.fixture
def fake_user_config(tmp_path, monkeypatch):
    """Write a fake user.json and point SKILLCTL_USER_CONFIG at it."""
    config_file = tmp_path / "user.json"
    config_file.write_text(
        json.dumps(
            {
                "library_path": "~/my-skills",
                "scan_paths": [
                    {"path": "~/a", "scope": "global", "priority": "high"},
                    {"path": "~/b", "scope": "project", "priority": "low"},
                ],
                "default_flags": {"update_timeout": 120},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SKILLCTL_USER_CONFIG", str(config_file))
    return config_file


def test_load_user_config_returns_empty_when_file_missing(clean_env):
    """No env, no user.json → empty dict (never raises)."""
    from user_config import load_user_config
    cfg = load_user_config()
    assert cfg == {}


def test_load_user_config_reads_explicit_path(clean_env, fake_user_config):
    """SKILLCTL_USER_CONFIG points to a JSON file; loader reads it."""
    from user_config import load_user_config
    cfg = load_user_config()
    assert cfg["library_path"] == "~/my-skills"
    assert len(cfg["scan_paths"]) == 2


def test_load_user_config_returns_empty_on_invalid_json(clean_env, tmp_path, monkeypatch):
    """Invalid JSON → empty dict (no exception leaks to caller)."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("SKILLCTL_USER_CONFIG", str(bad))

    from user_config import load_user_config
    cfg = load_user_config()
    assert cfg == {}


def test_get_library_path_expands_user(fake_user_config):
    """`~/my-skills` expands to a real user home path."""
    from user_config import load_user_config, get_library_path
    cfg = load_user_config()
    p = get_library_path(cfg)
    assert p is not None
    assert str(p).startswith(str(Path.home()))
    assert str(p).endswith("my-skills")


def test_get_scan_paths_returns_normalized_list(fake_user_config):
    """Each entry expands ~ and defaults missing scope/priority."""
    from user_config import load_user_config, get_scan_paths
    cfg = load_user_config()
    paths = get_scan_paths(cfg)
    assert len(paths) == 2
    # Both ~ should be expanded
    assert "~" not in paths[0]["path"]
    # Defaults applied
    assert paths[0]["scope"] == "global"  # explicit
    assert paths[0]["priority"] == "high"  # explicit


def test_get_default_flag_returns_value_or_default(fake_user_config):
    """Existing flag returns its value; missing flag returns default."""
    from user_config import load_user_config, get_default_flag
    cfg = load_user_config()
    assert get_default_flag(cfg, "update_timeout") == 120
    assert get_default_flag(cfg, "missing", "fallback") == "fallback"
    assert get_default_flag(cfg, "missing") is None


def test_resolve_library_path_prefers_env_var(fake_user_config, monkeypatch):
    """SKILL_LIBRARY_PATH wins over user.json."""
    monkeypatch.setenv("SKILL_LIBRARY_PATH", "/tmp/from-env")
    from user_config import resolve_library_path
    p = resolve_library_path()
    assert p == Path("/tmp/from-env")


def test_resolve_library_path_falls_back_to_user_json(fake_user_config):
    """No env var → user.json's library_path."""
    from user_config import resolve_library_path
    p = resolve_library_path()
    assert p is not None
    assert str(p).endswith("my-skills")


def test_resolve_library_path_returns_none_when_unconfigured(clean_env):
    """Neither env nor user.json → None (caller decides how to handle)."""
    from user_config import resolve_library_path
    assert resolve_library_path() is None
