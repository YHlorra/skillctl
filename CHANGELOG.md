# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [5.0.0] - Unreleased

### Breaking changes

- **`install`, `adopt`, `migrate` are now mandatory 2-gated.** Every skill entering the library must pass `validate --strict` (structural + security + red-flag) and `score` (8-dim quality) before landing.
- **New flags**: `--gate-mode enforce|skip` (default `enforce`), `--no-gate` (escape hatch, warns loudly), `--non-interactive` (auto-confirm on pass; for CI / agents).
- **`--yes` semantic shift**: still skips the post-gate user prompt, but is only valid AFTER gates pass. For "trust the source, skip gates" use `--no-gate`.
- **TTY auto-detection**: prompts auto-disable in non-TTY (e.g. LLM agent stdin). Explicit `--non-interactive` flag remains for clarity in CI logs.

### New exit codes

- `3` — gate report emitted, user declined (interactive only)
- `4` — gate failure (validate --strict failed)

### Added

- `scripts/_lib/gates.py`: shared gate evaluation helper. Runs validate + score as subprocesses, assembles frozen `GateReport` dataclass, formats human-readable report.
- Gate evaluation wired into `scan_and_index.py` install path (clone to tmp dir → gate → atomic move to library).
- Gate evaluation wired into `adopt_skills.py` (per-skill gate in discovery loop; failures skip + continue).
- Gate evaluation wired into `migrate_nested_to_main.py` (per-skill gate; failures skip + continue).

### Changed

- `scripts/skillctl.py` `PASSTHROUGH_FLAGS`: added `--gate-mode`, `--no-gate`, `--non-interactive`.
- `tests/test_install.py`: all 5 install invocations now use `--non-interactive` to avoid hanging on gate prompt.
- `references/recipes.md`: 9 L2 command invocations updated with `--non-interactive` or `--no-gate`.

### Forward-looking only

- v5 is forward-looking. Skills already in the library (imported under v4) were not retroactively gated. For manual audit of existing skills:
  ```bash
  skillctl validate --strict --json <existing-skill-path> | jq .all_valid
  python scripts/score.py --skill <existing-skill-name>
  ```
  A future `audit` command is on the roadmap.

## [4.0.0] - 2026-06-24

### Added

- `scripts/adopt_skills.py`: implements `skillctl adopt` (was previously routed to a missing script). Discovers unmanaged skills in source dir (default `~/.claude/skills/`), copies them to the library, and replaces source with a junction/symlink. Flags: `--dry-run`, `--yes`, `--backup`, `--rebuild-index`, `--source`, `--library`.
- `scripts/scan_and_index.py --enrich`: GitHub API inference for orphan skills' `github_url`, gated behind `--enrich` flag (off by default; preserves zero-network default).
- `skillctl score` 4 sub-commands: `score track`, `score regressions`, `score history-report`, `score trend <name>` routed to `score_history.py`.

### Added (tests)

- `test_help_lists_v4_commands`: verifies all 16 v4 commands present.
- `test_help_excludes_dead_commands`: verifies cull/remediate/toggle/map/state/library absent.
- `test_score_subcommands_route`: smoke for score sub-commands (non-127 routing).
- `test_adopt_dry_run_does_not_modify`: verify adopt --dry-run is non-destructive.
- `test_scan_enrich_flag_exists`: verify `--enrich` documented in scan --help.
- `test_status_reports_v4`: verify status JSON reports `skillctl_version: "4.0"`.
- `test_unknown_command_still_errors`: removed commands return "unknown" not 127.

### Removed (commands)

- `skillctl cull`, `remediate`, `toggle`, `map`, `state`: removed.
  These were routed in `COMMANDS` dict but had no backing scripts
  (`exit 127: script not found`). User-facing intent was either
  already covered by other commands (`cleanup --interactive`,
  `validate --fix`, `list --info`, `status`) or never used.
- `skillctl library`: removed. Routed to `scripts/skill_library.py`
  (28889 B), but zero hits in `references/recipes.md`, `tests/`,
  `CONTRIBUTING.md`. The `skill_library.py` script is deleted in
  a later phase.

### Removed (scripts)

- `scripts/scan_all.py`: orphan after `--enrich` was ported into
  `scan_and_index.py` in Phase 5.
- `scripts/scan_and_check.py`: fully redundant + double-call bug.
- `scripts/update_helper.py`: zero importers; `backup_skill()` never called.
- `scripts/fetch_github_info.py`: only docstring reference at
  scan_and_index.py:293; never imported.
- `scripts/skill_library.py`: routed command removed in Phase 4; no callers.
- `scripts/scoring/` (entire package): half-finished refactor;
  `scripts/score.py` does not import from it.

### Changed

- COMMANDS dict in `scripts/skillctl.py`: 22 → 16 entries
  (init, scan, install, list, adopt, link, dedup, delete, update,
  validate, cleanup, migrate, score, rollback, status, help).
- `skillctl_version` reported by `status`: 3.0 → 4.0.
- `PASSTHROUGH_FLAGS`: `--source` restored (needed by `skillctl adopt --source`).

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

[4.0.0]: https://github.com/your-org/skillctl/compare/v3.1.0...v4.0.0
[Unreleased]: https://github.com/your-org/skillctl/compare/v4.0.0...HEAD
[3.1.0]: https://github.com/your-org/skillctl/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/your-org/skillctl/releases/tag/v3.0.0
