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


def test_install_reinstall_backs_up_and_refreshes(run_skillctl, sandbox_lib, fake_source_repo):
    """--reinstall backs up working tree and refreshes via fetch+reset."""
    # First install
    r1 = run_skillctl("install", "--non-interactive", fake_source_repo.as_uri())
    assert r1.returncode == 0

    # Mutate one skill in the wrapper to verify backup captures working tree
    wrapper = sandbox_lib / "fake"
    target_file = wrapper / "skill1" / "SKILL.md"
    original_content = target_file.read_text(encoding="utf-8")
    target_file.write_text(original_content + "\n# local edit\n", encoding="utf-8")

    # Reinstall
    r2 = run_skillctl("install", "--non-interactive", "--reinstall", fake_source_repo.as_uri())
    assert r2.returncode == 0, f"reinstall failed: {r2.stderr}"

    # Backup dir exists with the local edit
    backup_root = sandbox_lib / ".skillctl-backup"
    assert backup_root.is_dir(), f"missing backup dir {backup_root}"
    backups = list(backup_root.iterdir())
    assert len(backups) == 1, f"expected 1 backup, got {backups}"
    backup = backups[0]
    backed_up_skill = backup / "skill1" / "SKILL.md"
    assert backed_up_skill.is_file()
    assert "local edit" in backed_up_skill.read_text(encoding="utf-8")

    # Wrapper content was refreshed (local edit gone)
    assert "local edit" not in target_file.read_text(encoding="utf-8")
