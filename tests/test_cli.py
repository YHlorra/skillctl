"""Smoke tests for skillctl CLI dispatch (skillctl.py main).

Covers:
- `skillctl help` lists commands including the new `install`
- Unknown command exits non-zero with a clear error
- `skillctl install <unknown-url>` surfaces git clone errors gracefully
"""
import subprocess
import sys

from conftest import SKILLCTL_ROOT, SCRIPTS_DIR


def test_help_lists_install_command(run_skillctl):
    result = run_skillctl("help")
    # skillctl help may write to stderr or stdout depending on impl
    combined = result.stdout + result.stderr
    assert "install" in combined.lower(), f"install not mentioned in help output:\n{combined}"


def test_unknown_command_exits_nonzero(run_skillctl):
    result = run_skillctl("this-command-does-not-exist")
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unknown" in combined.lower() or "error" in combined.lower()


def test_install_invalid_url_exits_nonzero(run_skillctl, sandbox_lib):
    """install with non-existent URL should fail, not crash silently."""
    result = run_skillctl("install", "https://github.com/nonexistent-org-xyz-12345/does-not-exist.git")
    assert result.returncode != 0
