"""Shared pytest fixtures for skillctl smoke tests.

All tests run against a sandboxed library root via SKILL_LIBRARY_PATH env.
No test touches the host's real skill library.
"""
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Path to skillctl root (parent of tests/)
SKILLCTL_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = SKILLCTL_ROOT / "scripts"


@pytest.fixture
def sandbox_lib(tmp_path) -> Path:
    """A clean per-test library directory."""
    lib = tmp_path / "lib"
    lib.mkdir()
    return lib


@pytest.fixture
def skillctl_env(sandbox_lib) -> dict:
    """Env vars for invoking skillctl scripts against sandbox_lib."""
    return {
        **os.environ,
        "SKILL_LIBRARY_PATH": str(sandbox_lib),
        # Force UTF-8 output on Windows
        "PYTHONIOENCODING": "utf-8",
    }


@pytest.fixture
def skillctl_bin() -> Path:
    """Path to scripts/skillctl.py."""
    return SCRIPTS_DIR / "skillctl.py"


@pytest.fixture
def run_skillctl(skillctl_env, skillctl_bin):
    """Callable that runs `python scripts/skillctl.py <args>` against sandbox_lib.

    Returns a CompletedProcess with stdout/stderr captured as text.
    """
    def _run(*args, timeout=120):
        return subprocess.run(
            [sys.executable, str(skillctl_bin), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=skillctl_env,
            cwd=str(SKILLCTL_ROOT),
            timeout=timeout,
        )
    return _run


@pytest.fixture
def fake_source_repo(tmp_path) -> Path:
    """Build a bare git repo with N skill subdirs, return its URL.

    The repo is a bare mirror so `git clone file://...` works.
    """
    work = tmp_path / "work"
    bare = tmp_path / "fake.git"
    work.mkdir()

    # Initialize working repo
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=str(work), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.invalid"],
        cwd=str(work), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(work), check=True, capture_output=True,
    )

    # Create 3 skill subdirs with SKILL.md each
    for i in range(1, 4):
        skill_dir = work / f"skill{i}"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            textwrap.dedent(f"""\
                ---
                name: skill{i}
                description: test skill {i}
                ---
                # skill{i}
                """),
            encoding="utf-8",
        )

    subprocess.run(["git", "add", "-A"], cwd=str(work), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--quiet"],
        cwd=str(work), check=True, capture_output=True,
    )

    # Create bare mirror
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(work), str(bare)],
        check=True, capture_output=True,
    )
    return bare


@pytest.fixture
def broken_skill_repo(tmp_path) -> Path:
    """A bare git repo with one clean skill and one broken skill.

    - good-skill: passes validate --strict
    - bad-skill: fails validate --strict (missing 'name' field)
    """
    work = tmp_path / "broken-work"
    bare = tmp_path / "broken.git"
    work.mkdir()

    subprocess.run(["git", "init", "--quiet"], cwd=str(work), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.invalid"],
        cwd=str(work), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(work), check=True, capture_output=True,
    )

    # Clean skill (passes gates)
    good = work / "good-skill"
    good.mkdir()
    (good / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            name: good-skill
            description: a clean skill that passes gate
            ---
            # good-skill
            """),
        encoding="utf-8",
    )

    # Broken skill (fails validate --strict: missing 'name')
    bad = work / "bad-skill"
    bad.mkdir()
    (bad / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            description: broken skill with no name field
            ---
            # bad-skill
            """),
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "-A"], cwd=str(work), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=str(work), check=True, capture_output=True)
    subprocess.run(
        ["git", "clone", "--bare", "--quiet", str(work), str(bare)],
        check=True, capture_output=True,
    )
    return bare


def assert_clean_lib(lib: Path):
    """Assert that lib contains no leftover test pollution."""
    if not lib.exists():
        return
    leftovers = []
    for p in lib.iterdir():
        if p.name == ".skillctl-backup":
            # After auto-commit, only empty date buckets may remain.
            # Flag any per-op backup dir (non-empty descendant).
            for child in p.iterdir():
                if any(child.iterdir()):
                    leftovers.append(child)
            continue
        leftovers.append(p)
    # Test cleanup happens automatically via tmp_path fixture teardown,
    # but this is a defensive check during the test.
    assert not leftovers, f"Test left leftover dirs in {lib}: {leftovers}"
