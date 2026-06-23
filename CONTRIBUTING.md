# Contributing to skillctl

Thanks for your interest. skillctl is a small, focused tool — small enough
that you can read every script under `scripts/` in an afternoon. We aim to
keep it that way.

## Development setup

```bash
# Clone
git clone https://github.com/your-org/skillctl.git
cd skillctl

# Install the only non-stdlib dep
pip install pyyaml pytest

# Verify scripts compile
python -c "import py_compile; import glob; [py_compile.compile(f) for f in glob.glob('scripts/*.py')]"

# Run tests
pytest tests/ -v
```

Python 3.10+ is required. The code uses `from __future__ import` style is
not used; we rely on stdlib typing features that are 3.10+.

## Code layout

- `scripts/skillctl.py` — thin argparse dispatcher. Maps subcommand names
  to underlying scripts. Adds no logic of its own beyond arg
  transformation and indexing `COMMANDS`.
- `scripts/<verb>.py` — one CLI script per action (scan, install, adopt,
  migrate, etc.). Each script is a standalone `argparse` program. They are
  intentionally NOT importable as modules — they are invoked via
  `subprocess.run`.
- `references/` — documentation: recipes, CLI spec, architecture notes,
  governance rules.
- `SKILL.md` — the agent-facing description (used by agent runners that
  auto-discover skills). Routing table, command matrix, and recipes are
  the source of truth for users.

## Coding conventions

- **No new third-party deps** without discussion. PyYAML is the only
  external dep and we want to keep it that way. Stdlib first.
- **Stdlib only for HTTP** — use `urllib.request`, never `requests`.
- **Paths as `pathlib.Path`** — never string concatenation. Use
  `Path / "subdir"` not `os.path.join`.
- **Backslashes in strings**: avoid. If you must (Windows paths), use raw
  strings `r"C:\path"` or `Path("C:/path")`.
- **Print to stdout, errors to stderr**. Exit codes: `0` ok, `1` business
  error, `2` CLI usage error, `127` script-not-found.
- **Write to `.skillctl-backup/` for destructive ops** (matching the
  `adopt` convention of `.skill-adopt-backup/`). Never overwrite a
  user's existing data without a backup.
- **Per-repo error tolerance** for bulk operations like `update --repos`:
  one repo failing must not abort the batch. Aggregate errors and report.

## Adding a new subcommand

1. Add your script under `scripts/<name>.py` as a standalone argparse
   program.
2. Register it in `scripts/skillctl.py`:
   - Add `"<name>": "<name>.py"` to the `COMMANDS` dict.
   - If your script uses new flags, add them to `PASSTHROUGH_FLAGS`.
3. Update `SKILL.md`:
   - Add a row to the routing table.
   - Add a row to the command matrix table.
4. Update `references/cli-spec.md` with a `### <name>` section.
5. Add a recipe in `references/recipes.md` if there's a common scenario.
6. Add a smoke test in `tests/test_<name>.py`.
7. Update `CHANGELOG.md` under `[Unreleased]`.

## Tests

We use `pytest`. Tests live under `tests/` and run against a sandboxed
library root (via `SKILL_LIBRARY_PATH` env override). No tests touch the
host's real skill library.

Run: `pytest tests/ -v`

Tests are subprocess-based: each test calls `python scripts/<x>.py ...`
with `SKILL_LIBRARY_PATH` pointing at a tempdir. This matches the real
deployment shape (skillctl is invoked as a CLI, not imported as a lib).

## Pull request process

1. Fork the repo and create a feature branch: `git checkout -b feat/<name>`
2. Make your change. Keep commits focused; one logical change per commit.
3. Add or update tests for any new behavior.
4. Update `CHANGELOG.md` under `[Unreleased]` with a one-line entry.
5. Verify: `pytest tests/ -v` passes locally.
6. Open a PR. Fill in the PR template. Reference any related issue.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat: <description>` — new feature
- `fix: <description>` — bug fix
- `refactor: <description>` — no behavior change
- `docs: <description>` — docs only
- `test: <description>` — tests only
- `chore: <description>` — maintenance

Examples from this repo:
- `feat(skillctl): expose install subcommand + update --repos`
- `fix(scan_and_index): collision detection on install`

## Release process

Maintainers cut releases by:
1. Bumping the version in `SKILL.md` description if needed.
2. Moving the `[Unreleased]` section in `CHANGELOG.md` to a dated release
   section.
3. Tagging: `git tag -a v<X>.<Y>.<Z> -m "..."`.
4. Pushing tags: `git push origin main v<X>.<Y>.<Z>`.

We follow SemVer. Backward-incompatible changes bump the major; new
features bump the minor; fixes and docs bump the patch.

## Questions

Open a GitHub issue with the `question` label. No separate mailing list or
chat for now.
