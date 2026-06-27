"""Smoke tests for `skillctl install <url>` and `--reinstall`.

Covers:
- Fresh install creates parent wrapper with .git/ and skill subdirs
- Collision detection refuses when target exists and is non-empty
- --reinstall backs up working tree and refreshes in place
"""
import shutil

from conftest import SKILLCTL_ROOT


def test_install_creates_parent_wrapper_with_git(run_skillctl, sandbox_lib, fake_source_repo):
    """Fresh install: <lib>/<repo>/.git/ + skill subdirs preserved."""
    result = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())

    assert result.returncode == 0, f"install failed: {result.stderr}"
    assert "Installed to" in result.stdout

    # Wrapper name = repo basename with .git suffix stripped
    wrapper = sandbox_lib / "fake"
    assert wrapper.is_dir(), f"wrapper missing: {wrapper}"
    assert (wrapper / ".git").is_dir(), "wrapper must preserve .git/"

    # Skill subdirs preserved under the wrapper
    for i in range(1, 4):
        skill = wrapper / f"skill{i}"
        assert skill.is_dir(), f"missing {skill}"
        assert (skill / "SKILL.md").is_file()


def test_install_collision_refuses_without_reinstall(run_skillctl, sandbox_lib, fake_source_repo):
    """Second install to same path refuses with actionable message."""
    # First install: succeeds
    r1 = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())
    assert r1.returncode == 0

    # Second install: refuses
    r2 = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())
    assert r2.returncode != 0, "second install must fail"
    combined = r2.stdout + r2.stderr
    assert "Path exists" in combined
    assert "--reinstall" in combined


def test_install_reinstall_refreshes_without_leaving_backup(run_skillctl, sandbox_lib, fake_source_repo):
    """--reinstall refreshes in place; backup auto-removes on success since v6 unified backup layer; only failure retains."""
    # First install
    r1 = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())
    assert r1.returncode == 0

    # Mutate one skill in the wrapper to verify refresh actually happened
    wrapper = sandbox_lib / "fake"
    target_file = wrapper / "skill1" / "SKILL.md"
    original_content = target_file.read_text(encoding="utf-8")
    target_file.write_text(original_content + "\n# local edit\n", encoding="utf-8")

    # Reinstall
    r2 = run_skillctl("install", "--non-interactive", "--reinstall", fake_source_repo.as_uri())
    assert r2.returncode == 0, f"reinstall failed: {r2.stderr}"

    # Wrapper content was refreshed (local edit gone)
    assert "local edit" not in target_file.read_text(encoding="utf-8")

    # Backup root may exist (date buckets persist), but per-op backup dirs must be gone
    backup_root = sandbox_lib / ".skillctl-backup"
    if backup_root.is_dir():
        leftover = [p for p in backup_root.rglob("install-fake_*") if p.is_dir()]
        assert not leftover, f"backup not auto-removed: {leftover}"
