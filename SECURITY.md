# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 3.1.x (latest) | Yes |
| 3.0.x | Best-effort |
| < 3.0 | No |

## Reporting a vulnerability

**Do not open a public GitHub issue for security bugs.**

Email: `<maintainer-email>` (replace with actual address before publishing).

Please include:
1. Description of the vulnerability
2. Steps to reproduce
3. Affected version(s)
4. Potential impact

You should receive an acknowledgement within 72 hours. We aim to ship a
fix within 14 days for critical issues and 30 days for non-critical.

## Scope

`skillctl` is a local CLI tool. It does not run a network service. The
attack surface is:

- **Skill content**: `skillctl` reads `SKILL.md` from any path under the
  configured library. A malicious `SKILL.md` with crafted YAML could
  attempt to exploit the YAML parser. We use `yaml.safe_load` exclusively
  to mitigate this.
- **Git URLs**: `skillctl install <url>` and `skillctl update --repos`
  invoke `git` with URLs. Only clone repos you trust. HTTPS URLs are
  recommended; SSH URLs require you to have already trusted the host.
- **Filesystem operations**: `--reinstall` writes to a backup directory
  and refreshes via `git reset --hard`. This is destructive of local
  uncommitted changes — review the message before running.

## Out of scope

- Vulnerabilities in upstream dependencies (PyYAML, git, Python).
  Report those upstream.
- Issues in skills installed via `skillctl install`. Those are
  independent projects.
