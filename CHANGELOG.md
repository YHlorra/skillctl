# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [3.1.0] - 2026-06-23

### Added

- `skillctl install <github-url>`: clone a repo as a parent wrapper with
  `.git/` preserved, so `git pull` updates work.
- `skillctl install --reinstall <url>`: collision-resistant reinstall that
  backs up the working tree to `<library>/.skillctl-backup/<ts>/<repo>/`
  and refreshes in place via `git fetch && git reset --hard origin/HEAD`.
- `skillctl update --repos`: bulk `git pull --ff-only` every direct-child
  `.git/` directory under the library root. Catches both multi-skill
  wrapper repos and per-skill `.git` installs in one pass.
- `skillctl update --repos --dry-run`: preview which repos would be pulled.
- `skillctl update --repos --library <path>`: override the library root
  (default: `SKILL_LIBRARY_PATH` env or skillctl canonical).
- `skillctl update --repos --timeout <seconds>`: per-repo timeout override
  (default: 60s).
- Routing table in `SKILL.md` now distinguishes `install`, `link`, and
  `adopt`; documents the three install paradigms.
- Reference docs: new `Recipe 0` (install from GitHub), expanded
  `Recipe 5` (update with `--repos`), new `Recipe 13` (install error
  recovery).

### Changed

- `scripts/check_updates.py`: new `update_wrapper_repos()` filesystem-driven
  path, mutually exclusive with the existing index-driven `--skill` path.
- `scripts/skillctl.py`: new `install` subcommand wired to
  `scan_and_index.py`; new passthrough flags `--install`, `--repos`,
  `--reinstall`, `--execute`, `--timeout`, `--library`; special arg
  transform so `skillctl install <url>` injects `--install` before the URL.
- `scripts/scan_and_index.py`: `install_from_github()` gains `reinstall`
  and `backup_dir` parameters with collision detection; argparse gains
  `--reinstall` flag.
- `scan_and_index.py` symlink utilities simplified (removed
  `_symlink_cache`, `get_physical_path`); dedup logic refactored (removed
  `KNOWN_NESTED_REPOS` hard-coded set, replaced with simpler duplicate
  detection by real_path).

### Backward compatibility

- No existing commands or flags removed.
- `skillctl scan --install <url>` still works (now also accepts
  `--reinstall`).
- `skillctl update` (no `--repos`) unchanged behavior.
- New wrapper repos in your library are auto-discovered by
  `update --repos` (backfill benefit, no extra config).

## [3.0.0] - 2026-04-29

Initial public-shape release. 18 Python scripts unified under
`skillctl.py` CLI; SKILL.md frontmatter; scan / link / adopt / dedup /
update / validate / cleanup / migrate subcommands.

[Unreleased]: https://github.com/your-org/skillctl/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/your-org/skillctl/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/your-org/skillctl/releases/tag/v3.0.0
