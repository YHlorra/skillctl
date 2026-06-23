# User Configuration (`user.json`)

`skillctl` does not commit a per-user config file. Each operator
maintains their own `user.json` on their local machine, in an
XDG-compliant location.

This file is intentionally **not** in version control. See
`.gitignore`:

```
scan-config.yaml
.canonical_path
user.json
```

## Where the file lives

| Platform | Default location |
|---|---|
| Linux | `$XDG_CONFIG_HOME/skillctl/user.json` or `~/.config/skillctl/user.json` |
| macOS | `~/Library/Application Support/skillctl/user.json` |
| Windows | `%APPDATA%\skillctl\user.json` (resolves to `C:\Users\<user>\AppData\Roaming\skillctl\user.json`) |

Override the path with the `SKILLCTL_USER_CONFIG` env var.

## Schema

All fields are optional. Missing keys are silently treated as unset.

```json
{
  "library_path": "C:/Users/me/skills",
  "scan_paths": [
    {"path": "~/.claude/skills",        "scope": "global",  "priority": "high"},
    {"path": "~/projects/foo/.claude/skills", "scope": "project", "priority": "medium"}
  ],
  "default_flags": {
    "update_timeout": 60
  }
}
```

| Field | Type | Default if unset | Meaning |
|---|---|---|---|
| `library_path` | string | empty | Canonical library root. Resolved by `scripts/user_config.py:resolve_library_path()`. |
| `scan_paths` | array of object | empty | List of dirs to scan. Each has `path` (str), `scope` (`global`/`local`/`project`), `priority` (`high`/`medium`/`low`). |
| `default_flags.<flag>` | varies | unset | Per-flag defaults applied by individual scripts. Currently only `update_timeout` is consumed. |

## Resolution order

For `library_path` (the most-used field), scripts check sources in this
order — first match wins:

1. `SKILL_LIBRARY_PATH` env var
2. `user.json` `library_path` field
3. Error: script exits with a message pointing here

This order means:
- CI / one-shot use: set the env var, no file needed.
- Daily use: drop a `user.json` once, forget about it.
- Fresh checkout: scripts refuse to run with a hard-coded Windows path;
  you must opt in.

## How scripts use it

The resolution helper is `scripts/user_config.py`:

```python
from user_config import resolve_library_path, load_user_config

lib = resolve_library_path()         # Path or None
if lib is None:
    sys.exit("configure SKILL_LIBRARY_PATH or user.json")

cfg = load_user_config()
scan_paths = cfg.get("scan_paths", [])
default_timeout = cfg.get("default_flags", {}).get("update_timeout", 60)
```

The helper is XDG-compliant and never raises on missing file. It
returns an empty dict / None when the file is absent, so scripts
degrade gracefully.

## Minimal example

Save this as `~/.config/skillctl/user.json` (Linux) or
`%APPDATA%\skillctl\user.json` (Windows):

```json
{
  "library_path": "~/skills",
  "scan_paths": [
    {"path": "~/skills", "scope": "global", "priority": "high"},
    {"path": "~/.claude/skills", "scope": "global", "priority": "high"}
  ]
}
```

Then any `skillctl` command will resolve to your library without
needing the env var.

## Why this design

1. **No leaks**: Per-user paths (Windows user names, machine-specific
   locations) never enter version control. Cloning the repo on a
   different machine doesn't pollute your config.
2. **XDG-compliant**: Standard Unix locations for personal config;
   matches macOS conventions; falls back to `%APPDATA%` on Windows.
3. **No hard-coded defaults**: Scripts that previously had
   `BASE_DIR = Path(r"E:\\Desktop\\Skills")` now refuse to run until
   configured. This is intentional — every operator's library is
   different and there is no safe default.
4. **Environment override**: Power users and CI pipelines can skip
   the file entirely with `SKILL_LIBRARY_PATH`.

## Legacy: `scan-config.yaml` and `.canonical_path`

Before `user.json`, `skillctl` used two other config artifacts:

- `scan-config.yaml` — operator's YAML config in the repo root. Still
  supported by `scripts/scan_and_index.py` for `scan_paths` lookup,
  but the canonical_path field is now ignored (use `user.json`).
- `.canonical_path` — single-line text file in the repo root
  containing one absolute path. Still supported by
  `get_canonical_path()` as a fallback. Both legacy files are
  gitignored.

If you're starting fresh, prefer `user.json` — it's the documented path
forward and the only one documented in `README.md`.
