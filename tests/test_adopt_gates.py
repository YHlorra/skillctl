"""Gate tests for `skillctl adopt`.

Covers:
- Gate failure in one skill skips only that skill (others proceed)
- All-clean adopt succeeds
"""
import shutil
import subprocess
import textwrap

import pytest


def test_adopt_gate_fail_skips_skill(run_skillctl, sandbox_lib, broken_skill_repo):
    """Broken skill fails gate; only good-skill is adopted, bad-skill is skipped."""
    # broken_skill_repo is a bare git repo; clone to working dir for adopt
    # (adopt operates on local directories, not git URLs)
    source_root = sandbox_lib.parent / "broken-source"
    subprocess.run(
        ["git", "clone", "--quiet", str(broken_skill_repo), str(source_root)],
        check=True, capture_output=True,
    )

    result = run_skillctl(
        "adopt",
        "--non-interactive", "--yes",
        "--source", str(source_root),
        "--library", str(sandbox_lib),
    )

    assert result.returncode == 0, (
        f"adopt failed (expected 0, partial ok): {result.stderr}"
    )

    # good-skill should be in the library
    good_skill = sandbox_lib / "good-skill"
    assert good_skill.is_dir(), (
        f"good-skill should be adopted; library contents: {list(sandbox_lib.iterdir())}"
    )
    assert (good_skill / "SKILL.md").is_file()

    # bad-skill should NOT be in the library (gate failed)
    bad_skill = sandbox_lib / "bad-skill"
    assert not bad_skill.is_dir(), (
        f"bad-skill should NOT be adopted (gate failed); "
        f"library: {list(sandbox_lib.iterdir())}"
    )

    # Output should mention gate failure for bad-skill
    combined = result.stdout + result.stderr
    assert "bad-skill" in combined, "bad-skill gate failure not mentioned"
    assert "FAIL" in combined or "Gate failure" in combined, (
        "Gate failure not reported for bad-skill"
    )


def test_adopt_all_clean_succeeds(run_skillctl, sandbox_lib, fake_source_repo):
    """All skills clean: adopt succeeds for all."""
    # fake_source_repo is a bare git repo; clone to working dir for adopt
    source_root = sandbox_lib.parent / "clean-source"
    source_root.mkdir()

    subprocess.run(
        ["git", "clone", "--quiet", str(fake_source_repo), str(source_root)],
        check=True, capture_output=True,
    )

    result = run_skillctl(
        "adopt",
        "--non-interactive", "--yes",
        "--source", str(source_root),
        "--library", str(sandbox_lib),
    )

    assert result.returncode == 0, f"adopt failed: {result.stderr}"

    # All 3 skills should be in the library
    for i in range(1, 4):
        skill = sandbox_lib / f"skill{i}"
        assert skill.is_dir(), f"skill{i} should be adopted"
        assert (skill / "SKILL.md").is_file()
