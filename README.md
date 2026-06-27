<a id="readme-top"></a>

[![License][license-shield]][license-url]
[![Version][version-shield]][version-url]
[![Last Commit][last-commit-shield]][last-commit-url]
[![Issues][issues-shield]][issues-url]

<br />
<div align="center">
  <h3 align="center">skillctl</h3>

  <p align="center">
    A single CLI for the messy job of managing a local Skills library.<br />
    Scan, install from GitHub, link to agent dirs, dedup, validate,
    bulk-update — all from <code>python scripts/skillctl.py &lt;command&gt;</code>.
    <br />
    <a href="https://github.com/YHlorra/skillctl"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/YHlorra/skillctl/issues">Report Bug</a>
    ·
    <a href="https://github.com/YHlorra/skillctl/issues">Request Feature</a>
  </p>
</div>

> **v5.0.0 — current development.** Mandatory 2-gate protocol on every
> `install` / `adopt` / `migrate`. Unified backup layer (`scripts/_lib/backup.py`)
> for all write operations; `delete` is intentionally irreversible (3-second
> abort window + `--yes` to skip). 14 functional scripts + dispatcher, no
> daemon, no telemetry. See [CHANGELOG](./CHANGELOG.md).

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#configuration">Configuration</a></li>
    <li><a href="#testing">Testing</a></li>
    <li><a href="#deployment">Deployment</a></li>
    <li><a href="#security">Security</a></li>
    <li><a href="#architecture">Architecture</a></li>
    <li><a href="#usage">Usage</a>
      <ul>
        <li><a href="#command-reference">Command Reference</a></li>
        <li><a href="#three-install-paradigms">Three Install Paradigms</a></li>
        <li><a href="#example-end-to-end-first-install">Example: End-to-End First Install</a></li>
        <li><a href="#library-path-resolution">Library Path Resolution</a></li>
        <li><a href="#platform-notes">Platform Notes</a></li>
        <li><a href="#safety">Safety</a></li>
      </ul>
    </li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About The Project

You have many skill folders, each its own `SKILL.md`, spread across
multiple agents and projects. When you install a multi-skill repo from
GitHub you want to **keep its parent wrapper with `.git/` so `git pull`
updates work** — not flatten it to N sibling folders.

`skillctl` solves this with a thin `argparse` dispatcher
(`scripts/skillctl.py`) on top of v5.0.0 — 14 functional scripts + dispatcher.
One command, one job — no framework, no daemon, no remote calls.

```text
scan → list → install → link → update → dedup → validate → cleanup
   │             │                 │
   │             │                 └─ bulk `git pull --ff-only` every wrapper
   │             └─ clone as parent wrapper (preserves .git/)
   └─ rebuild index.json (no network)
```

Everything runs locally. No network calls, no telemetry, no file mutation
without an explicit `--yes`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python][python-shield]][python-url] — single runtime requirement
* [![PyYAML][pyyaml-shield]][pyyaml-url] — only non-stdlib dep
* [![Git][git-shield]][git-url] — used for clone / fetch / pull / reset
* `argparse`, `pathlib`, `subprocess` — stdlib only beyond the above

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

Get a local copy running in under a minute. `skillctl` ships as a
checkout-and-run tool — no `pip install` of the tool itself, just the
one non-stdlib dep.

### Prerequisites

* **Python 3.10 or newer** — `python --version` should print `3.10` or
  above
* **Git on `PATH`** — `git --version`; used for clone / fetch / pull /
  reset
* **PyYAML + pytest** — the only non-stdlib dependencies
  ```sh
  pip install -r requirements.txt
  ```

### Installation

1. **Clone the repository**
   ```sh
   git clone https://github.com/YHlorra/skillctl.git
   cd skillctl
   ```

2. **Put `scripts/` on `PATH`** (or invoke directly)
   ```sh
   # Option A — add to PATH for this shell
   export PATH="$PWD/scripts:$PATH"

   # Option B — invoke the dispatcher directly
   python scripts/skillctl.py <command>
   ```

3. **Set your library path** — see [Configuration](#configuration) below
   for the full resolution chain.
   ```sh
   # Recommended: per-user, XDG-compliant
   mkdir -p ~/.config/skillctl
   echo '{"library_path": "~/skills"}' > ~/.config/skillctl/user.json

   # Or: one-off env override
   export SKILL_LIBRARY_PATH="$HOME/skills"
   ```

4. **Scan and verify**
   ```sh
   skillctl scan --config scan-config.yaml
   skillctl list --json | head
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Configuration

`skillctl` does **not** commit a per-user config — every operator's
library path is different, so each user maintains their own on their
local machine. Pick one — first match wins:

| # | Source | Where | Best for |
|---|---|---|---|
| 1 | `SKILL_LIBRARY_PATH` env var | shell | CI, one-shot use |
| 2 | `user.json` (XDG-compliant) | `~/.config/skillctl/user.json` (Linux/macOS), `%APPDATA%\skillctl\user.json` (Windows) | Daily use |
| 3 | `scan-config.yaml` (legacy) | repo root | Older setups |
| 4 | `.canonical_path` (legacy) | repo root, single-line text | Fallback only |

**Recommended — `user.json`:**

```json
{
  "library_path": "~/skills",
  "scan_paths": [
    {"path": "~/skills", "scope": "global", "priority": "high"},
    {"path": "~/.claude/skills", "scope": "global", "priority": "high"}
  ]
}
```

**One-off env override:**

```sh
export SKILL_LIBRARY_PATH="$HOME/skills"
```

**Legacy — `scan-config.yaml`:**

Copy [`scan-config.example.yaml`](scan-config.example.yaml) to
`scan-config.yaml` and fill in your paths.

> **Never commit `user.json` or `scan-config.yaml`** — both contain
> absolute paths to your local machine. The `.gitignore` already
> excludes them.

Full schema and resolution chain:
[`references/user-config.md`](references/user-config.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Testing

We use `pytest`. Tests live under `tests/` and run against a sandboxed
library root via the `SKILL_LIBRARY_PATH` env override. No test touches
the host's real skill library.

```sh
pip install pytest
pytest tests/ -v
```

Tests are subprocess-based: each test calls `python scripts/<x>.py ...`
with `SKILL_LIBRARY_PATH` pointing at a tempdir. This matches the real
deployment shape — `skillctl` is invoked as a CLI, not imported as a
library.

CI runs on every push to `main` via
[`.github/workflows/test.yml`](.github/workflows/test.yml) across Python
3.10, 3.11, and 3.12.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Deployment

`skillctl` ships as a git checkout — there is no container, package, or
remote service to deploy. "Deployment" here means making `skillctl`
available on another machine:

```sh
# On the target machine
git clone https://github.com/YHlorra/skillctl.git
cd skillctl
pip install pyyaml
export PATH="$PWD/scripts:$PATH"

# Per-user config (XDG-compliant)
mkdir -p ~/.config/skillctl
cp /path/to/your/user.json ~/.config/skillctl/user.json
```

The `.gitignore` excludes `user.json`, `scan-config.yaml`, and
`.canonical_path` so per-machine state never leaves the host. Library
state itself lives under the operator's chosen `library_path` and is
expected to be backed up separately (e.g. via the host's dotfiles repo
or a dedicated backup).

If you want to pin a version, use a git tag:

```sh
git clone --branch v5.0.0 https://github.com/YHlorra/skillctl.git
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Security

See [SECURITY.md](SECURITY.md) for disclosure policy.

`skillctl` is a local CLI tool with no network service. The only remote
interaction is `git` itself, invoked by `install` and `update`. We use
`yaml.safe_load` exclusively to mitigate crafted-YAML attacks against
`SKILL.md` frontmatter.

**Supported versions:** 5.0.x (active, unreleased on `main`), 4.0.x (best-effort), 3.x (best-effort).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Architecture

`skillctl` is a thin `argparse` dispatcher (`scripts/skillctl.py`) that
maps subcommand names to standalone scripts under `scripts/`. The shared
helpers (gate evaluation, TTY-aware prompts) live under `scripts/_lib/`.

```text
┌──────────────────────────────────────────────────┐
│  scripts/skillctl.py — argparse + subprocess     │
│  (PASSTHROUGH_FLAGS, COMMANDS dict, 3 built-ins) │
└─────────────────┬────────────────────────────────┘
                  │ subprocess.run([python, <script>, *args])
                  ▼
┌──────────────────────────────────────────────────┐
│  scripts/ — 14 functional scripts + 1 dispatcher │
│  ┌──────────────────────────┐                    │
│  │ scripts/_lib/ (v5+)      │                    │
│  │   gates.py    GateReport │  ← shared by all   │
│  │   tty.py      prompt /   │     L2 commands    │
│  │              TTY detect  │                    │
│  │   backup.py   create/    │  ← all write ops   │
│  │              commit/keep │     route here     │
│  │   paths.py    expand/    │  ← shared by all   │
│  │              symlink     │     scripts        │
│  └──────────────────────────┘                    │
└──────────────────────────────────────────────────┘
```

Each top-level script is a self-contained `argparse` program. They are
intentionally **not** importable as modules — they are invoked via
`subprocess.run`. This keeps the deployment shape honest: `skillctl` is
a CLI, not a library. The `_lib/` namespace is the exception: it holds
helpers that **are** importable and shared across the L2 scripts.

Key scripts and their jobs:

| Script | Job |
|---|---|
| `scan_and_index.py` | Build `index.json` from disk; gated `install <url>` (clone-to-tmp → gate → atomic move) |
| `list_skills.py` | List indexed skills |
| `check_updates.py` | Git remote diff; bulk `git pull --ff-only` |
| `adopt_skills.py` | Per-skill gate + junction adoption of `~/.claude/skills/` |
| `collect_and_link.py` | Symlink library skills into an agent dir |
| `deduplicate.py` | Detect and resolve physical duplicates |
| `cleanup.py` | Remove orphan symlinks / stale entries |
| `migrate_nested_to_main.py` | Per-skill gate + flatten nested wrapper repos |
| `governance_validate.py` | Validate every `SKILL.md` against the schema (Gate 1) |
| `score.py` + `score_history.py` | 8-dimension quality scoring (Gate 2, informational) |
| `user_config.py` | XDG-compliant user.json resolution chain |
| `git_rollback.py` | Git rollback for `rollback` command |
| `skillctl.py` | The dispatcher itself — arg transform + `COMMANDS` index |
| `_lib/gates.py` | Run validate + score, assemble frozen `GateReport` |
| `_lib/tty.py` | TTY-aware prompt / auto-detect non-interactive |
| `_lib/backup.py` | Unified backup layer — `create_backup` / `commit_backup` / `keep_backup` (single source of truth for adopt / install --reinstall / link / migrate) |
| `_lib/paths.py` | Path expansion, symlink / junction detection, git-repo probe |

State files (auto-managed, never committed):

| File | Created by | Purpose |
|---|---|---|
| `<root>/index.json` | `scan` | The library index |
| `<root>/.skillctl/state.json` | `init` | CLI-level state cache |
| `<root>/.omc/state/last-tool-error.json` | any script | Last error trace for recovery |
| `<lib>/.skillctl-backup/<YYYY-MM-DD>/<op>-<target>_<HHMMSS>/` | adopt / install --reinstall / link / migrate | Unified backup directory. Auto-removed on success, retained on failure (location recorded in `last-tool-error.json`). `delete` is excluded by design — it's irreversible, self-backup via `cp` / `mv` is the contract. |

Detailed design notes:
[`references/architecture.md`](references/architecture.md).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

### Command Reference

| Command | What it does | Key flags |
|---|---|---|
| `skillctl init` | Initialize `.skillctl/` state | — |
| `skillctl status` | Status overview (JSON) | — |
| `skillctl scan` | Rebuild `index.json` from disk | `--config` `--output` |
| `skillctl install <url>` | Clone a multi-skill repo as a parent wrapper (keeps `.git/`) | `--reinstall` |
| `skillctl list` | List skills in the library | `--path` `--index` `--filter` |
| `skillctl update` | Detect Git remote updates | `--fetch` `--skill` |
| `skillctl update --repos` | Bulk `git pull --ff-only` every wrapper | `--dry-run` `--library` `--timeout` |
| `skillctl adopt` | Adopt local `~/.claude/skills/` dirs as junctions (v5: gated) | `--dry-run` `--yes` `--backup` `--non-interactive` `--no-gate` `--gate-mode` |
| `skillctl link` | Symlink library skills into a target agent dir | `--target` `--skills` `--dry-run` |
| `skillctl dedup` | Detect and resolve duplicate skills | `--strategy` `--dry-run` |
| `skillctl validate` | Governance + safety check on all `SKILL.md` | `--strict` `--fix` |
| `skillctl cleanup` | Remove orphan symlinks / stale entries | `--dry-run` `--remove` |
| `skillctl migrate` | Flatten nested wrapper repos into top-level skills | `--dry-run` `--execute` |
| `skillctl rollback` | Git rollback | `--to` |
| `skillctl score` | Internal skill scoring | — |
| `skillctl help` | Full command list | — |

Run `skillctl <cmd> --help` for the full flag matrix of any command.
Full reference: [`references/cli-spec.md`](references/cli-spec.md).

### Three Install Paradigms

`skillctl` exposes three ways to bring a repo into your library — pick
by scenario, not by convenience:

| Paradigm | Command | Physical layout | Use when | v5 Gate |
|---|---|---|---|---|
| **GitHub wrapper install** | `skillctl install <url>` | `<lib>/<repo>/.git/ + skills/` | You want `git pull` to keep the repo up to date | ✅ Required |
| **Local junction adoption** | `skillctl adopt` | `~/.claude/skills/<name>` → junction → `<lib>/<name>` | Adopting a skill dir that's already on your machine | ✅ Required |
| **Flatten to top-level** | `skillctl migrate` | `<lib>/<name>/` (parent kept) | You want each skill at the top level, not under a wrapper | ✅ Required |

`install` and `migrate` are inverses by design.

### Example: End-to-End First Install

```sh
# 1. Install a multi-skill repo from GitHub as a wrapper
skillctl install https://github.com/YHlorra/multi-skill-repo

# 2. Refresh the index so the new skills are visible
skillctl scan

# 3. Preview a bulk update before pulling anything
skillctl update --repos --dry-run

# 4. Actually pull
skillctl update --repos

# 5. Validate governance on the whole library
skillctl validate --strict
```

### Library Path Resolution

`skillctl` resolves your library root in this order — first match wins:

1. `SKILL_LIBRARY_PATH` environment variable
2. `~/.config/skillctl/user.json` (XDG-compliant; per-user, never committed)
3. `<repo>/scan-config.yaml` (legacy)
4. `<repo>/.canonical_path` (legacy, single-line text file)

### Platform Notes

* **Windows** — Works with Developer Mode enabled (for symlinks). Falls
  back to junctions automatically. `install --reinstall` uses
  `git fetch && git reset --hard origin/HEAD` in place to dodge Windows
  file-lock issues on `.git/objects/pack/*`.
* **Linux / macOS** — No special setup. Symlinks work natively.

### Safety

* All write operations (`adopt`, `link`, `cleanup`, `migrate`) require an
  explicit `--yes`. Run with `--dry-run` first.
* **`--yes` in v5**: skips the post-gate user confirmation prompt only.
  It does **not** bypass the gates themselves — use `--no-gate` for that
  (and accept the loud warning).
* **Unified backup layer** (v5+). `adopt`, `install --reinstall`, `link`,
  and `migrate` all snapshot to `<lib>/.skillctl-backup/<YYYY-MM-DD>/<op>-<target>_<HHMMSS>/`
  before mutating. Backups auto-delete on success, persist on failure
  (location recorded in `.omc/state/last-tool-error.json`).
* **`delete` is irreversible by design** — no backup, no `--backup` flag.
  A 3-second abort window with a "Ctrl-C to cancel" prompt is built in;
  `--yes` skips the countdown for scripted use. Self-backup with
  `cp -a <skill> /tmp/` if you want a safety net.
* No network calls. The only remote interaction is `git` itself, invoked
  by the `install` and `update` commands.
* No mutation of skill content. `skillctl` manages **location**
  (symlink / junction / clone) — it does not edit `SKILL.md` bodies.

### Mandatory Gates Protocol (v5+)

Every skill entering the library via `install`, `adopt`, or `migrate` must
pass two gates **before** any content is written:

| Gate | What it checks | Fails if |
|------|----------------|----------|
| Gate 1: `validate --strict` | SKILL.md structure, required fields, security, red-flags | Malformed frontmatter, missing fields, suspicious patterns |
| Gate 2: `score` (informational) | 8-dimension quality score | Never blocks — informational only |

**Override**: `--no-gate` skips both gates (NOT recommended — prints a loud
warning). For CI / agents: `--non-interactive` auto-confirms after gates pass.

```
# CI / agent flow
skillctl install --non-interactive https://github.com/user/repo

# Emergency bypass (not recommended)
skillctl adopt --source ~/.claude/skills --library ~/skills --no-gate
```

Gate failures on `install` abort the install. On `adopt` / `migrate` (which
operate on multiple skills), only the failing skill is skipped — the rest
continue.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup, code
layout, conventions, the new-subcommand checklist, and the PR process.

Quick start:

```sh
git clone https://github.com/YHlorra/skillctl.git
cd skillctl
pip install pyyaml pytest
pytest tests/ -v
```

For security issues, see [SECURITY.md](SECURITY.md) — please **do not**
file public issues for vulnerabilities.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for the
full text.

Copyright (c) 2026 skillctl contributors.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contact

Maintainer: [@YHlorra](https://github.com/YHlorra)

Project link: [https://github.com/YHlorra/skillctl](https://github.com/YHlorra/skillctl)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [Best-README-Template](https://github.com/othneildrew/Best-README-Template)
  — the structural inspiration for this README
* [Shields.io](https://shields.io) — badge generation
* [Keep a Changelog](https://keepachangelog.com/) — the CHANGELOG format
* [Semantic Versioning](https://semver.org/) — the version policy
* The Claude / Codex / OpenCode agent-skill conventions this tool targets
* Everyone who has filed an issue, sent a PR, or reported a regression

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

<!-- MARKDOWN LINKS & IMAGES -->
[license-shield]: https://img.shields.io/github/license/YHlorra/skillctl.svg?style=for-the-badge
[license-url]: https://github.com/YHlorra/skillctl/blob/main/LICENSE
[version-shield]: https://img.shields.io/github/v/tag/YHlorra/skillctl.svg?style=for-the-badge
[version-url]: https://github.com/YHlorra/skillctl/releases
[last-commit-shield]: https://img.shields.io/github/last-commit/YHlorra/skillctl.svg?style=for-the-badge
[last-commit-url]: https://github.com/YHlorra/skillctl/commits/main
[issues-shield]: https://img.shields.io/github/issues/YHlorra/skillctl.svg?style=for-the-badge
[issues-url]: https://github.com/YHlorra/skillctl/issues
[python-shield]: https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=ffd43b
[python-url]: https://www.python.org/downloads/
[pyyaml-shield]: https://img.shields.io/badge/PyYAML-required-yellow.svg?style=for-the-badge&logo=yaml&logoColor=white
[pyyaml-url]: https://pypi.org/project/PyYAML/
[git-shield]: https://img.shields.io/badge/git-required-f05033.svg?style=for-the-badge&logo=git&logoColor=white
[git-url]: https://git-scm.com/