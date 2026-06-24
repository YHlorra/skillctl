"""Gate tests for `skillctl install`.

Covers:
- Gate failure aborts install (broken skill returns exit 4)
- Gate pass lands the skill
- --no-gate bypasses gate with warning
- --non-interactive auto-confirms on gate pass
- --reinstall re-runs gates on existing install
"""
import pytest


def test_install_gate_fail_aborts(run_skillctl, sandbox_lib, broken_skill_repo):
    """Broken skill (missing name) fails Gate 1, install aborts with exit 4."""
    result = run_skillctl("install", "--non-interactive", broken_skill_repo.as_uri())

    assert result.returncode == 4, (
        f"Expected exit 4 (gate failure), got {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # Nothing should have landed
    assert not any(sandbox_lib.iterdir()), (
        f"Library should be empty after gate failure, found: {list(sandbox_lib.iterdir())}"
    )
    # Gate report should be printed
    assert "Gate 1" in result.stdout, "Gate report missing from output"
    assert "FAIL" in result.stdout, "Gate failure not reported"


def test_install_gate_pass_lands(run_skillctl, sandbox_lib, fake_source_repo):
    """Clean skill passes gates, install lands successfully."""
    # --non-interactive auto-confirms after gates pass; --yes not needed for install
    result = run_skillctl(
        "install", "--non-interactive", fake_source_repo.as_uri()
    )

    assert result.returncode == 0, f"install failed: {result.stderr}"
    wrapper = sandbox_lib / "fake"
    assert wrapper.is_dir(), f"wrapper missing: {wrapper}"
    assert (wrapper / ".git").is_dir(), ".git/ must be preserved"
    # All 3 skills should be present
    for i in range(1, 4):
        skill = wrapper / f"skill{i}"
        assert skill.is_dir(), f"missing {skill}"
        assert (skill / "SKILL.md").is_file()


def test_install_no_gate_skips(run_skillctl, sandbox_lib, broken_skill_repo):
    """--no-gate bypasses gate, installs even the broken skill (with warning)."""
    result = run_skillctl(
        "install", "--no-gate", "--non-interactive", broken_skill_repo.as_uri()
    )

    assert result.returncode == 0, (
        f"--no-gate install should succeed, got {result.returncode}.\n"
        f"stderr: {result.stderr}"
    )
    # Broken skill should have landed despite gate failure
    wrapper = sandbox_lib / "broken"
    assert wrapper.is_dir(), f"wrapper missing after --no-gate install: {wrapper}"


def test_install_non_interactive_gate_pass_auto_lands(
    run_skillctl, sandbox_lib, fake_source_repo
):
    """--non-interactive auto-confirms after gates pass (no --yes needed)."""
    result = run_skillctl(
        "install", "--non-interactive", fake_source_repo.as_uri()
    )

    assert result.returncode == 0, f"install failed: {result.stderr}"
    wrapper = sandbox_lib / "fake"
    assert wrapper.is_dir(), f"wrapper missing: {wrapper}"


def test_install_reinstall_re_gates(run_skillctl, sandbox_lib, fake_source_repo):
    """--reinstall re-runs gates on already-installed wrapper."""
    # First install: succeeds
    r1 = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())
    assert r1.returncode == 0, f"first install failed: {r1.stderr}"

    # Second install with --reinstall: gates must re-run
    r2 = run_skillctl(
        "install", "--non-interactive", "--reinstall", fake_source_repo.as_uri()
    )
    assert r2.returncode == 0, f"reinstall failed: {r2.stderr}"

    # Gate report should appear again (re-run gates)
    assert "Gate" in r2.stdout, "Gates not re-run on reinstall"

    wrapper = sandbox_lib / "fake"
    assert wrapper.is_dir()
    assert (wrapper / ".git").is_dir()
