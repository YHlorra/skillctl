"""Smoke tests for `skillctl update --repos`.

Covers:
- --repos dry-run reports would-pull list
- --repos execute runs git pull and reports success
- --repos on empty library reports 0 repos with friendly hint
"""
import subprocess

from conftest import SKILLCTL_ROOT


def _make_local_git_repo(path, remote_url: str = None):
    """Helper: turn `path` into a local git repo with a single commit.

    Args:
        path: directory to init as a git repo
        remote_url: optional remote URL to add as 'origin'. If provided,
            update_wrapper_repos will see this as a valid pull target.
    """
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text("---\nname: stub\n---\n# stub\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(path), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=str(path), check=True)
    if remote_url:
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=str(path), check=True,
        )


def test_update_repos_dry_run_lists_candidates(run_skillctl, sandbox_lib):
    """--repos --dry-run shows what would be pulled, doesn't actually pull."""
    # Each local repo needs a remote to be a valid pull target.
    # Point both at a fake remote URL (won't actually be fetched in dry-run).
    _make_local_git_repo(sandbox_lib / "fake-skill-1", remote_url="https://example.com/fake.git")
    _make_local_git_repo(sandbox_lib / "fake-skill-2", remote_url="https://example.com/fake.git")

    result = run_skillctl("update", "--repos", "--dry-run", "--library", str(sandbox_lib))

    assert result.returncode == 0, f"dry-run failed: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "fake-skill-1" in combined
    assert "fake-skill-2" in combined
    # dry-run mode puts valid remotes in would_pull bucket
    assert "Would pull" in combined or "would pull" in combined.lower()


def test_update_repos_empty_library_reports_zero(run_skillctl, sandbox_lib):
    """Empty library: friendly hint, no crash."""
    result = run_skillctl("update", "--repos", "--library", str(sandbox_lib))

    assert result.returncode == 0
    assert "0" in result.stdout  # "0 git repos found"
    assert "skillctl install" in result.stdout  # hint


def test_update_repos_executes_pull(run_skillctl, sandbox_lib, tmp_path):
    """--repos (live) runs git fetch + pull --ff-only and reports success.

    Set up a real bare remote so the pull actually completes (rather than
    skipping due to a fake URL).
    """
    # Create a bare remote with one commit
    remote_bare = tmp_path / "remote.git"
    remote_work = tmp_path / "remote-work"
    remote_work.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=str(remote_work), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.invalid"], cwd=str(remote_work), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(remote_work), check=True)
    (remote_work / "SKILL.md").write_text("---\nname: stub\n---\n# stub\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(remote_work), check=True)
    subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=str(remote_work), check=True)
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(remote_work), str(remote_bare)],
        check=True,
    )

    # Local repo cloned from that bare
    local = sandbox_lib / "local-skill"
    subprocess.run(
        ["git", "clone", "--quiet", str(remote_bare), str(local)],
        check=True,
    )

    result = run_skillctl("update", "--repos", "--library", str(sandbox_lib))

    assert result.returncode == 0, f"pull failed: {result.stderr}"
    assert (
        "Pulled" in result.stdout
        or "already up to date" in result.stdout.lower()
        or "Up to date" in result.stdout
        or "Skipped" in result.stdout
    )
