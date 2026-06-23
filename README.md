<!--
GitHub renders README.md by default regardless of browser language.
For a Chinese version, copy this file to README.zh-CN.md and translate
the section bodies (anchors stay the same).
-->

<a id="readme-top"></a>

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url]
[![Python 3.10+][python-shield]][python-url]

<div align="center">
  <h3 align="center">skillctl</h3>

  <p align="center">
    A single CLI for the messy job of managing a local Skills library.<br />
    Scan, index, install from GitHub, link to agent dirs, dedup,
    validate, and bulk-update — all from <code>python scripts/skillctl.py &lt;command&gt;</code>.
    <br />
    <a href="https://github.com/<!-- TODO: owner -->/skillctl"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="#usage">View Demo</a>
    ·
    <a href="https://github.com/<!-- TODO: owner -->/skillctl/issues">Report Bug</a>
    ·
    <a href="https://github.com/<!-- TODO: owner -->/skillctl/issues">Request Feature</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
        <li><a href="#three-install-paradigms">Three install paradigms</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a>
      <ul>
        <li><a href="#command-reference">Command reference</a></li>
        <li><a href="#library-path-resolution">Library path resolution</a></li>
        <li><a href="#platform-notes">Platform notes</a></li>
      </ul>
    </li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About The Project

You have many skill folders, each its own `SKILL.md`, spread across multiple
agents and projects. When you install a multi-skill repo from GitHub you want
to **keep its parent wrapper with `.git/` so `git pull` updates work** —
not flatten it to N sibling folders.

`skillctl` solves this with a thin `argparse` dispatcher (`scripts/skillctl.py`)
on top of 18 small Python files under `scripts/`. One command, one job —
no framework, no daemon, no remote calls.

```text
scan → list → install → link → update → dedup → validate → cleanup
   │              │                │
   │              │                └─ bulk `git pull --ff-only` every wrapper
   │              └─ clone as parent wrapper (preserves .git/)
   └─ rebuild index.json (no network)
```

Everything runs locally. No network calls, no telemetry, no file mutation
without an explicit `--yes`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python 3.10+][python-shield]][python-url] — single runtime requirement
* [![PyYAML][pyyaml-shield]][pyyaml-url] — only non-stdlib dep
* [![Git][git-shield]][git-url] — used for clone / fetch / pull / reset
* `argparse`, `pathlib`, `subprocess` — stdlib only beyond the above

### Three install paradigms

`skillctl` exposes three ways to bring a repo into your library — pick by
scenario, not by convenience:

| Paradigm | Command | Physical layout | Use when |
| --- | --- | --- | --- |
| **GitHub wrapper install** | `skillctl install <url>` | `<lib>/<repo>/.git/ + skills/` | You want `git pull` to keep the repo up to date |
| **Local junction adoption** | `skillctl adopt` | `~/.claude/skills/<name>` → junction → `<lib>/<name>` | Adopting a skill dir that's already on your machine |
| **Flatten to top-level** | `skillctl migrate` | `<lib>/<name>/` (parent kept) | You want each skill at the top level, not under a wrapper |

`install` and `migrate` are inverses by design.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

### Prerequisites

* **Python 3.10 or newer** — `python --version` should print `3.10` or above
* **Git on `PATH`** — `git --version`; used for clone / fetch / pull / reset
* **PyYAML** — the only non-stdlib dependency
  ```sh
  pip install pyyaml
  ```

### Installation

1. **Clone the repository**
   ```sh
   git clone https://github.com/<!-- TODO: owner -->/skillctl.git
   cd skillctl
   ```

2. **Put `scripts/` on `PATH`** (or invoke directly)
   ```sh
   # Option A — add to PATH for this shell
   export PATH="$PWD/scripts:$PATH"

   # Option B — invoke the dispatcher directly
   python scripts/skillctl.py <command>
   ```

3. **Set your library path** — pick one (first match wins, see
   [Library path resolution](#library-path-resolution) below)
   ```sh
   # Recommended: per-user, XDG-compliant
   mkdir -p ~/.config/skillctl
   echo '{"library_path": "E:\\Desktop\\Skills"}' > ~/.config/skillctl/user.json

   # Or: one-off env override
   export SKILL_LIBRARY_PATH="$HOME/skills"
   ```

4. **Scan and verify**
   ```sh
   skillctl scan --config scan-config.yaml
   skillctl list --json | head
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

### Command reference

| Command | What it does | Key flags |
| --- | --- | --- |
| `skillctl install <url>` | Clone a multi-skill repo as a parent wrapper (keeps `.git/`) | `--reinstall` |
| `skillctl scan` | Rebuild `index.json` from disk | `--config` `--output` `--no-auto-nested` |
| `skillctl list` | List skills in the library | `--path` `--index` `--filter` |
| `skillctl update` | Detect Git remote updates | `--fetch` `--skill` |
| `skillctl update --repos` | Bulk `git pull --ff-only` every wrapper | `--dry-run` `--library` `--timeout` |
| `skillctl adopt` | Adopt local `~/.claude/skills/` dirs as junctions | `--dry-run` `--yes` `--backup` |
| `skillctl link` | Symlink library skills into a target agent dir | `--target` `--skills` `--dry-run` |
| `skillctl dedup` | Detect and resolve duplicate skills | `--strategy` `--dry-run` |
| `skillctl validate` | Governance + safety check on all `SKILL.md` | `--strict` `--fix` |
| `skillctl cleanup` | Remove orphan symlinks / stale entries | `--dry-run` `--remove` |
| `skillctl migrate` | Flatten nested wrapper repos into top-level skills | `--dry-run` `--execute` |
| `skillctl help` | Full command list | — |

Run `skillctl <cmd> --help` for the full flag matrix of any command.
Full reference: [`references/cli-spec.md`](references/cli-spec.md).

### Example: end-to-end first install

```sh
# 1. Install a multi-skill repo from GitHub as a wrapper
skillctl install https://github.com/<!-- TODO: owner -->/multi-skill-repo

# 2. Refresh the index so the new skills are visible
skillctl scan

# 3. Preview a bulk update before pulling anything
skillctl update --repos --dry-run

# 4. Actually pull
skillctl update --repos

# 5. Validate governance on the whole library
skillctl validate --strict
```

### Library path resolution

`skillctl` resolves your library root in this order — first match wins:

1. `SKILL_LIBRARY_PATH` environment variable
2. `~/.config/skillctl/user.json` (XDG-compliant; per-user, never committed)
3. `<repo>/scan-config.yaml` (legacy)
4. `<repo>/.canonical_path` (legacy, single-line text file)

To bootstrap: copy `scan-config.example.yaml` to `scan-config.yaml` in the
repo root and fill in your paths, **or** set `SKILL_LIBRARY_PATH` in your
shell, **or** create `~/.config/skillctl/user.json` with `library_path`.

> **Never commit `user.json` or `scan-config.yaml`** — both contain absolute
> paths to your local machine. The `.gitignore` already excludes them.

### Platform notes

* **Windows** — Works with Developer Mode enabled (for symlinks). Falls
  back to junctions automatically. `install --reinstall` uses
  `git fetch && git reset --hard origin/HEAD` in place to dodge Windows
  file-lock issues on `.git/objects/pack/*`.
* **Linux / macOS** — No special setup. Symlinks work natively.

### Safety

* All write operations (`adopt`, `link`, `delete`, `cleanup`, `migrate`)
  require an explicit `--yes`. Run with `--dry-run` first.
* `--backup <dir>` snapshots the working tree before destructive ops.
* No network calls. The only remote interaction is `git` itself, invoked
  by the `install` and `update` commands.
* No mutation of skill content. `skillctl` manages **location**
  (symlink / junction / clone) — it does not edit `SKILL.md` bodies.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Roadmap

`skillctl` tracks a [Semantic Versioning](https://semver.org/) release
line. See [`CHANGELOG.md`](CHANGELOG.md) for what shipped in each version.

* **v3.1.x (current line)** — `install` from GitHub, `update --repos`,
  three install paradigms, governance validation
* **v3.2+** — see [open issues](https://github.com/<!-- TODO: owner -->/skillctl/issues)
  for the proposed backlog

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Contributions are what make the open source community such a great place
to learn, inspire, and create. Any contribution you make is **greatly
appreciated**.

1. Fork the project
2. Create your feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a pull request

For development setup, test instructions, coding conventions, and the PR
review checklist, see [`CONTRIBUTING.md`](CONTRIBUTING.md).
For security issues, see [`SECURITY.md`](SECURITY.md) — please **do not**
file public issues for vulnerabilities.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for the
full text.

Copyright (c) 2026 skillctl contributors.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contact

<!-- TODO: Add maintainer contact info here. Suggested fields:
     - GitHub: @<!-- TODO: owner -->
     - Email: <!-- TODO: email -->
     - Project link: https://github.com/<!-- TODO: owner -->/skillctl
-->

Project link: [https://github.com/<!-- TODO: owner -->/skillctl](https://github.com/<!-- TODO: owner -->/skillctl)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [Best-README-Template](https://github.com/othneildrew/Best-README-Template)
  — the structural inspiration for this README
* [Shields.io](https://shields.io) — badge generation
* The Claude / Codex / OpenCode agent-skill conventions this tool targets
* Everyone who has filed an issue, sent a PR, or reported a regression

<p align="right">(<a href="#readme-top">back to top</a>)</p>

---

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/<!-- TODO: owner -->/skillctl.svg?style=for-the-badge
[contributors-url]: https://github.com/<!-- TODO: owner -->/skillctl/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/<!-- TODO: owner -->/skillctl.svg?style=for-the-badge
[forks-url]: https://github.com/<!-- TODO: owner -->/skillctl/network/members
[stars-shield]: https://img.shields.io/github/stars/<!-- TODO: owner -->/skillctl.svg?style=for-the-badge
[stars-url]: https://github.com/<!-- TODO: owner -->/skillctl/stargazers
[issues-shield]: https://img.shields.io/github/issues/<!-- TODO: owner -->/skillctl.svg?style=for-the-badge
[issues-url]: https://github.com/<!-- TODO: owner -->/skillctl/issues
[license-shield]: https://img.shields.io/github/license/<!-- TODO: owner -->/skillctl.svg?style=for-the-badge
[license-url]: https://github.com/<!-- TODO: owner -->/skillctl/blob/master/LICENSE
[python-shield]: https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge
[python-url]: https://www.python.org/downloads/
[pyyaml-shield]: https://img.shields.io/badge/PyYAML-required-yellow.svg?style=for-the-badge
[pyyaml-url]: https://pypi.org/project/PyYAML/
[git-shield]: https://img.shields.io/badge/git-required-f05033.svg?style=for-the-badge&logo=git&logoColor=white
[git-url]: https://git-scm.com/
