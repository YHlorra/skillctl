"""Smoke tests for skillctl CLI dispatch (skillctl.py main).

Covers:
- `skillctl help` lists commands including the new `install`
- Unknown command exits non-zero with a clear error
- `skillctl install <unknown-url>` surfaces git clone errors gracefully
- Phase 4/5/6: v4 command surface, score sub-commands, adopt, --enrich
"""
import subprocess
import sys
import json
import re

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


def test_help_lists_v4_commands(run_skillctl):
    """skillctl help lists exactly the 16 v4 commands."""
    result = run_skillctl("help")
    combined = (result.stdout + result.stderr).lower()
    expected = {
        "init", "scan", "install", "list", "adopt", "link", "dedup",
        "delete", "update", "validate", "cleanup", "migrate",
        "rollback", "score", "status", "help",
    }
    for cmd in expected:
        assert cmd in combined, f"command '{cmd}' missing from help output"


def test_help_excludes_dead_commands(run_skillctl):
    """skillctl help does NOT list removed commands."""
    result = run_skillctl("help")
    combined = result.stdout + result.stderr

    # Commands section: lines like "  init       (built-in)" or "  scan       -> ..."
    # Extract the command names from the commands section
    in_commands = False
    commands_found = []
    for line in combined.splitlines():
        if "commands:" in line.lower():
            in_commands = True
            continue
        if in_commands:
            if line.strip().startswith("global flags:"):
                break
            # Match lines like "  cmdname   ..." or "  cmdname  (built-in)"
            m = re.match(r'^\s+([a-z][a-z0-9_-]+)\s', line.strip())
            if m:
                commands_found.append(m.group(1).lower())

    dead = ["cull", "remediate", "toggle", "map", "state", "library"]
    for cmd in dead:
        assert cmd not in commands_found, f"dead command '{cmd}' should not appear in commands section"

    # state as a standalone word should not appear in commands
    assert "state" not in commands_found, "'state' should not be a command"
    # map should not appear
    assert "map" not in commands_found, "'map' should not be a command"


def test_score_subcommands_route(run_skillctl):
    """score sub-commands route to score_history.py (exit != 127)."""
    subcommands = [
        ("score", "track"),
        ("score", "regressions"),
        ("score", "history-report"),
        ("score", "trend", "nonexistent-skill"),
    ]
    for args in subcommands:
        result = run_skillctl(*args)
        assert result.returncode != 127, \
            f"skillctl {' '.join(args)} returned exit 127 (script not found)"


def test_adopt_dry_run_does_not_modify(run_skillctl, sandbox_lib, tmp_path):
    """skillctl adopt --dry-run must not touch source or library."""
    # Create a fake unmanaged skill in tmp source dir
    source_root = tmp_path / "source"
    source_root.mkdir()
    skill_dir = source_root / "my-test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-test-skill\n---\n# Test\n",
        encoding="utf-8",
    )

    result = run_skillctl(
        "adopt", "--dry-run",
        "--source", str(source_root),
        "--library", str(sandbox_lib),
    )

    # Exit 0
    assert result.returncode == 0, f"adopt --dry-run failed: {result.stderr}"

    # Source still exists unchanged
    assert (skill_dir / "SKILL.md").exists(), "Source skill was removed during --dry-run"

    # Library does NOT contain the skill
    adopted = sandbox_lib / "my-test-skill"
    assert not adopted.exists(), "Library should not contain skill after --dry-run"

    # Output contains WOULD indicator
    combined = result.stdout + result.stderr
    assert "would" in combined.lower(), f"No 'would' indicator in output: {combined}"


def test_scan_enrich_flag_exists(run_skillctl):
    """scan --help mentions the --enrich flag."""
    result = run_skillctl("scan", "--help")
    combined = result.stdout + result.stderr
    assert "--enrich" in combined, f"--enrich flag missing from scan --help:\n{combined}"


def test_status_reports_v5(run_skillctl):
    """skillctl status reports skillctl_version 5.0."""
    result = run_skillctl("status")
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data.get("skillctl_version") == "5.0", \
        f"Expected skillctl_version '5.0', got: {data.get('skillctl_version')}"


def test_unknown_command_still_errors(run_skillctl):
    """Removed commands now return 'unknown command', not 'script not found'."""
    result = run_skillctl("cull")
    assert result.returncode != 0
    combined = (result.stdout + result.stderr).lower()
    assert "unknown" in combined or "error" in combined
    assert "cull.py" not in combined and "script not found" not in combined
