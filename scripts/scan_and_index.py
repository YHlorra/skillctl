#!/usr/bin/env python3
"""
Skill Manager - Scan and Index Module

扫描多个目录，构建所有 skill 的统一索引。
支持：
- 直接扫描（skills 在根目录）
- 嵌套扫描（Git repo 风格的 skills/ 子目录）
- Glob 模式匹配

输出 index.json 包含所有 skill 的元数据和位置信息。
"""

import os
import sys
import json
import yaml
import subprocess
import shutil
import hashlib
import time
import re
import tempfile
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict
import argparse
from urllib.parse import quote_plus
from _lib.tty import should_prompt_user
from _lib.gates import run_gates, format_report
from _lib.backup import create_backup, commit_backup, keep_backup
from _lib.paths import expand_path, is_symlink, resolve_symlink_target
from _lib.paths import expand_path, is_symlink, resolve_symlink_target

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def get_canonical_path(config_path: Path = None) -> Path:
    """
    Get the canonical skill library path.

    Resolution chain (first match wins):

      1. ``SKILL_LIBRARY_PATH`` environment variable
      2. ``user.json`` ``library_path`` field (via ``resolve_library_path``)
      3. ``.canonical_path`` file in the skillctl directory (legacy)
      4. ``canonical_path`` in scan-config.yaml (legacy)

    If none of the above yields a usable path, the script exits with a
    message pointing the operator at ``references/user-config.md``. There
    is **no hard-coded default** — every operator's library is different
    and silently falling back to a leaked Windows path is the bug this
    function is designed to prevent.
    """
    # 1. Environment variable (highest priority)
    env_path = os.environ.get("SKILL_LIBRARY_PATH")
    if env_path:
        path = expand_path(env_path)
        if path.exists() or path.parent.exists():
            print(f"Using canonical path from SKILL_LIBRARY_PATH: {path}")
            return path

    # 2. user.json library_path (preferred over legacy .canonical_path file)
    try:
        from user_config import resolve_library_path
        resolved = resolve_library_path()
        if resolved is not None:
            if resolved.exists() or resolved.parent.exists():
                print(f"Using canonical path from user.json: {resolved}")
                return resolved
    except ImportError:
        pass

    skillctl_dir = Path(__file__).parent.parent

    # 3. .canonical_path file (legacy)
    canonical_file = skillctl_dir / ".canonical_path"
    if canonical_file.exists():
        try:
            lines = canonical_file.read_text().splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    canonical = line
                    path = expand_path(canonical)
                    if path.exists() or path.parent.exists():
                        print(f"Using canonical path from .canonical_path: {path}")
                        return path
                    break
        except Exception:
            pass

    # 4. Config file (legacy)
    if config_path and config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            canonical = config.get("canonical_path")
            if canonical:
                path = expand_path(canonical)
                if path.exists() or path.parent.exists():
                    print(f"Using canonical path from config: {path}")
                    return path
        except Exception:
            pass

    # 5. NO hard-coded default — refuse to guess
    sys.exit(
        "ERROR: Cannot determine skill library path.\n"
        "  Configure one of:\n"
        "    - env var SKILL_LIBRARY_PATH\n"
        "    - user.json field 'library_path' (see references/user-config.md)\n"
        "    - .canonical_path file in the skillctl directory (legacy)\n"
        "    - 'canonical_path' in scan-config.yaml (legacy)\n"
        "  See references/user-config.md for details."
    )

def hash_skill_files(skills: list) -> str:
    """
    Compute a hash of all skill file paths and modification times.
    Used to detect when skill files have changed since last scan.
    """
    hash_parts = []
    for skill in skills:
        for loc in skill.get("locations", []):
            skill_path = Path(loc["path"])
            if skill_path.exists():
                try:
                    mtime = skill_path.stat().st_mtime
                    hash_parts.append(f"{skill_path}:{mtime}")
                except OSError:
                    pass
    # Sort for consistent ordering
    hash_parts.sort()
    combined = "|".join(hash_parts)
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]

def get_git_info(skill_dir: Path) -> dict:
    """Get git information for a skill directory.

    For nested skills (e.g., Waza/skills/write), the .git is in the parent repo (Waza/.git).
    We check both skill_dir and its parents.
    """
    result = {
        "has_git": False,
        "remote_url": None,
        "current_hash": None,
        "branch": None,
        "commits_ahead": 0,
    }

    # Find the git repo root: check skill_dir, then parents
    git_cwd = None
    for check_dir in [skill_dir] + list(skill_dir.parents):
        git_dir = check_dir / ".git"
        if git_dir.exists() or (check_dir / ".git").is_file():
            git_cwd = check_dir
            break

    if git_cwd is None:
        return result

    try:
        proc = subprocess.run(
            ["git", "-C", str(git_cwd), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return result

        result["has_git"] = True

        branch = subprocess.run(
            ["git", "-C", str(git_cwd), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if branch.returncode == 0:
            result["branch"] = branch.stdout.strip()

        hash_proc = subprocess.run(
            ["git", "-C", str(git_cwd), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if hash_proc.returncode == 0:
            result["current_hash"] = hash_proc.stdout.strip()[:8]

        remote = subprocess.run(
            ["git", "-C", str(skill_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if remote.returncode == 0:
            result["remote_url"] = remote.stdout.strip()

        if result["remote_url"] and result["branch"]:
            try:
                fetch_proc = subprocess.run(
                    ["git", "-C", str(skill_dir), "fetch", "origin", "--quiet", "--timeout=5"],
                    capture_output=True,
                    timeout=8,
                )
                if fetch_proc.returncode == 0:
                    ahead = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(skill_dir),
                            "rev-list",
                            f"origin/{result['branch']}..HEAD",
                            "--count",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if ahead.returncode == 0:
                        result["commits_ahead"] = int(ahead.stdout.strip())
            except (subprocess.TimeoutExpired, Exception):
                pass

    except Exception:
        pass

    return result

def get_repo_info(url: str) -> dict:
    """Fetch GitHub repo info via git ls-remote."""
    clean_url = url.rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]

    repo_name = clean_url.split("/")[-1]

    latest_hash = "unknown"
    try:
        result = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            latest_hash = result.stdout.split()[0]
    except Exception:
        pass

    return {
        "name": repo_name,
        "url": url,
        "latest_hash": latest_hash,
    }

# ─── GitHub API (gated behind --enrich flag) ──────────────────────────────

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

def github_api_get(url, params=None):
    """GET request to GitHub API with rate limit handling."""
    import urllib.request
    import urllib.error

    full_url = f"https://api.github.com{url}"
    req = urllib.request.Request(full_url, headers=GITHUB_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            remaining = resp.headers.get("X-RateLimit-Remaining", "999")
            reset_ts = resp.headers.get("X-RateLimit-Reset", "")
            return data, int(remaining), int(reset_ts) if reset_ts else 0
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return None, 0, int(e.headers.get("X-RateLimit-Reset", 0))
        return None, 0, 0
    except Exception:
        return None, 0, 0

def wait_for_rate_limit(reset_ts):
    """Wait if rate limited."""
    if reset_ts > 0:
        wait_sec = reset_ts - time.time()
        if wait_sec > 0:
            print(f"[Rate limited] Waiting {int(wait_sec) + 5}s...", file=sys.stderr)
            time.sleep(wait_sec + 5)

# Known patterns: (skill_prefix, search_query_suffix, confidence)
KNOWN_PATTERNS = [
    ("agent-reach", "agent-reach/agent-reach", 1.0),
    ("x-tweet-fetcher", "skillcoder/x-tweet-fetcher", 0.8),
    ("last30days", "skillcoder/last30days", 0.8),
]

# Known org prefixes and their GitHub org/repo patterns
PREFIX_ORG_MAP = {
    "baoyu": None,
    "ljg": None,
    "money": None,
    "yao": "yao",
}

def infer_github_url(skill_name, skill_dir, rate_remaining, rate_reset):
    """
    Try to infer the GitHub URL for an orphan skill.
    Returns (url, method, confidence) or (None, None, 0).
    Only called when --enrich is set.
    """
    # 1. Check known patterns
    for prefix, known_url, conf in KNOWN_PATTERNS:
        if skill_name.startswith(prefix):
            return f"https://github.com/{known_url}", f"known_pattern:{prefix}", conf

    # 2. Try git remote if skill dir is a git repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(skill_dir),
            capture_output=True,
            text=True,
            timeout=5,
            windowsHide=True,
        )
        if result.returncode == 0:
            remote_url = result.stdout.strip()
            if remote_url.startswith("git@github.com:"):
                remote_url = "https://github.com/" + remote_url[15:].replace(".git", "")
            elif remote_url.startswith("https://github.com/"):
                remote_url = remote_url.replace(".git", "")
            if "github.com" in remote_url:
                return remote_url, "git_remote", 1.0
    except Exception:
        pass

    # 3. Try GitHub API search (if we have quota)
    if rate_remaining > 5:
        query = f"filename:SKILL.md {skill_name} in:path"
        search_url = f"/search/code?q={quote_plus(query)}&per_page=5"
        data, remaining, reset = github_api_get(search_url)
        new_remaining = min(rate_remaining, remaining)
        wait_for_rate_limit(reset)

        if data and "items" in data and len(data["items"]) > 0:
            item = data["items"][0]
            repo_url = f"https://github.com/{item['repository']['full_name']}"
            return repo_url, "github_api_search", 0.75

        # Fallback: search repos by name
        search_url2 = f"/search/repositories?q={quote_plus(skill_name)}+filename:SKILL.md&per_page=5"
        data2, remaining2, reset2 = github_api_get(search_url2)
        new_remaining = min(new_remaining, remaining2)
        wait_for_rate_limit(reset2)

        if data2 and "items" in data2 and len(data2["items"]) > 0:
            item = data2["items"][0]
            return (
                f"https://github.com/{item['full_name']}",
                "github_api_repo_search",
                0.6,
            )

        return None, "not_found", 0
    else:
        return None, "rate_limited", 0

def parse_skill_md(skill_md_path: Path) -> Optional[dict]:
    """Parse SKILL.md frontmatter and content."""
    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        parts = content.split("---")
        if len(parts) < 3:
            return None

        frontmatter = yaml.safe_load(parts[1])
        if not frontmatter:
            return None

        description = frontmatter.get("description", "")
        if isinstance(description, list):
            description = " ".join(description)
        description = description.replace("\n", " ").strip() if description else ""

        return {
            "name": frontmatter.get("name", skill_md_path.parent.name),
            "description": description[:200],
            "source_type": frontmatter.get("source_type", "local"),
            "github_url": frontmatter.get("github_url"),
            "github_hash": frontmatter.get("github_hash"),
            "version": frontmatter.get("version", "0.1.0"),
            "created_at": frontmatter.get("created_at"),
            "scope": frontmatter.get("scope", "project"),
            "entry_point": frontmatter.get("entry_point"),
            "dependencies": frontmatter.get("dependencies", []),
        }
    except Exception as e:
        print(f"Warning: Failed to parse {skill_md_path}: {e}", file=sys.stderr)
        return None

def find_skill_md_files(root_path: Path, auto_detect_nested: bool = True) -> List[Path]:
    """
    Find all SKILL.md files under root_path.

    If auto_detect_nested is True, also finds skills in nested patterns like:
    - skills/*/SKILL.md (GitHub-style repos)
    - */*/SKILL.md (any two-level deep)

    Excludes backup directories (starting with .backup).
    """
    skill_files = []

    # First: direct skill at root level (e.g., darwin-skill/SKILL.md)
    root_skill_md = root_path / "SKILL.md"
    if root_skill_md.exists():
        skill_files.append(root_skill_md)

    # Second: direct skills at root level via subdirectories
    for item in root_path.iterdir():
        if item.is_dir():
            # Skip backup directories
            if item.name.startswith(".backup"):
                continue
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill_files.append(skill_md)

    # Second: auto-detect nested patterns if enabled
    if auto_detect_nested:
        # Common nested patterns:
        # - skills/*/SKILL.md (ljg-skills style)
        # - */skills/*/SKILL.md
        # - */*/SKILL.md (any two levels, excluding backup dirs)
        # - .claude/skills/*/SKILL.md (project-level skills like E:\project\.claude\skills\skill-name\SKILL.md)

        for pattern in ["skills/*/SKILL.md", ".claude/skills/*/SKILL.md", "lark/*/SKILL.md"]:
            for match in root_path.glob(pattern):
                if match not in skill_files:
                    skill_files.append(match)

        # Also handle symlink/junction directories - glob doesn't follow symlinks, so we need iterdir
        for item in root_path.iterdir():
            if is_symlink(item) and item.is_dir():
                # This is a symlink to a directory - check for nested skills inside
                skills_dir = item / "skills"
                if skills_dir.exists():
                    for skill_dir in skills_dir.iterdir():
                        if skill_dir.is_dir():
                            skill_md = skill_dir / "SKILL.md"
                            if skill_md.exists() and skill_md not in skill_files:
                                skill_files.append(skill_md)

        # Skip backup directories in */*/SKILL.md pattern
        for backup_item in root_path.iterdir():
            if not backup_item.is_dir() or backup_item.name.startswith(".backup"):
                continue
            for match in (backup_item.glob("*/SKILL.md")):
                if match not in skill_files:
                    skill_files.append(match)

    return skill_files

def detect_git_repos_with_skills(root_path: Path) -> List[dict]:
    """
    Auto-detect Git repos that have skills subdirectories.
    Returns list of {repo_path, skills_path, git_url}
    """
    repos = []

    for item in root_path.iterdir():
        if not item.is_dir():
            continue

        # Skip backup directories
        if item.name.startswith(".backup"):
            continue

        # Check if it's a git repo
        if not (item / ".git").exists():
            continue

        # Check for skills/ subdirectory
        skills_dir = item / "skills"
        if skills_dir.exists() and skills_dir.is_dir():
            # Get git remote URL
            git_info = get_git_info(item)
            repos.append(
                {
                    "repo_path": str(item),
                    "skills_path": str(skills_dir),
                    "git_url": git_info.get("remote_url"),
                    "git_hash": git_info.get("current_hash"),
                }
            )

    return repos

def scan_directory(
    scan_path: Path,
    scope: str = "global",
    priority: str = "medium",
    auto_detect_nested: bool = True,
) -> list:
    """Scan a single directory for skills."""
    skills = []

    if not scan_path.exists():
        print(f"Warning: Path does not exist: {scan_path}", file=sys.stderr)
        return skills

    # Find all SKILL.md files
    skill_files = find_skill_md_files(scan_path, auto_detect_nested)

    for skill_md in skill_files:
        skill_dir = skill_md.parent

        metadata = parse_skill_md(skill_md)
        if not metadata:
            continue

        skill_name = metadata.get("name", skill_dir.name)

        # Check if symlink (for tracking) and ALWAYS resolve to get true physical path
        is_link = is_symlink(skill_dir)
        real_path = resolve_symlink_target(skill_dir)

        git_info = get_git_info(real_path)

        skill_entry = {
            "name": skill_name,
            "dir_name": skill_dir.name,
            "metadata": metadata,
            "locations": [
                {
                    "path": str(skill_dir),
                    "is_symlink": is_link,
                    "real_path": str(real_path),
                    "scope": scope,
                    "priority": priority,
                    "modified": datetime.fromtimestamp(
                        skill_dir.stat().st_mtime
                    ).isoformat()
                    if skill_dir.exists()
                    else None,
                }
            ],
            "git": git_info,
            "scan_path": str(scan_path),
        }

        skills.append(skill_entry)

    return skills

def build_index(
    scan_configs: list, output_path: Path = None, auto_detect_nested: bool = True
) -> dict:
    """Build comprehensive index from multiple scan paths."""
    all_skills = []
    skill_map = {}

    # First pass: detect nested Git repos with skills directories
    nested_repos = []
    for config in scan_configs:
        path = expand_path(config["path"])
        if path.exists() and config.get("auto_detect_nested", True):
            detected = detect_git_repos_with_skills(path)
            nested_repos.extend(detected)

    # Add detected nested repos to scan configs
    for repo in nested_repos:
        skills_dir = Path(repo["skills_path"])
        if not skills_dir.exists():
            continue

        for skill_md in find_skill_md_files(skills_dir, False):
            skill_dir = skill_md.parent
            metadata = parse_skill_md(skill_md)
            if not metadata:
                continue

            # Mark as coming from git repo
            metadata["source_type"] = "git_repo"
            metadata["repo_url"] = repo.get("git_url")

            # Check if symlink (for tracking) and ALWAYS resolve to get true physical path
            is_link = is_symlink(skill_dir)
            real_path = resolve_symlink_target(skill_dir)

            skill_name = metadata.get("name", skill_dir.name)
            git_info = get_git_info(skill_dir)

            skill_entry = {
                "name": skill_name,
                "dir_name": skill_dir.name,
                "metadata": metadata,
                "locations": [
                    {
                        "path": str(skill_dir),
                        "is_symlink": is_link,
                        "real_path": str(real_path),
                        "scope": "global",
                        "priority": "medium",
                        "modified": datetime.fromtimestamp(
                            skill_dir.stat().st_mtime
                        ).isoformat() if skill_dir.exists() else None,
                    }
                ],
                "git": git_info,
                "scan_path": str(skills_dir),
            }

            if skill_name in skill_map:
                skill_map[skill_name]["locations"].extend(skill_entry["locations"])
            else:
                skill_map[skill_name] = skill_entry
                all_skills.append(skill_entry)

    for scan_config in scan_configs:
        path = expand_path(scan_config["path"])
        scope = scan_config.get("scope", "global")
        priority = scan_config.get("priority", "medium")
        detect_nested = scan_config.get("auto_detect_nested", auto_detect_nested)

        print(
            f"Scanning: {path} (scope={scope}, priority={priority}, nested={detect_nested})"
        )
        skills = scan_directory(path, scope, priority, detect_nested)
        print(f"  Found {len(skills)} skills")

        for skill in skills:
            skill_name = skill["name"]

            if skill_name in skill_map:
                skill_map[skill_name]["locations"].extend(skill["locations"])
            else:
                skill_map[skill_name] = skill
                all_skills.append(skill)

    # Find true duplicates - same skill name but different real_path
    duplicates = []
    for name, skill in skill_map.items():
        # Get unique real_paths (resolve symlinks to their actual location)
        real_paths = set()
        for loc in skill["locations"]:
            real_paths.add(loc["real_path"])

        # If all locations point to the same real_path, it's not a duplicate
        # (just multiple symlinks pointing to the same skill)
        if len(real_paths) <= 1:
            continue

        # True duplicate: same name, different real locations
        real_locations = [loc for loc in skill["locations"] if not loc["is_symlink"]]
        symlink_locations = [loc for loc in skill["locations"] if loc["is_symlink"]]

        duplicates.append(
            {
                "name": name,
                "instances": [loc["path"] for loc in skill["locations"]],
                "real_instances": list(real_paths),
                "real_count": len(real_paths),
                "symlink_count": len(symlink_locations),
                "status": "conflict" if len(real_locations) > 1 else "resolved",
            }
        )

    index = {
        "version": "1.0",
        "scan_time": datetime.now().isoformat(),
        "scan_paths": [str(expand_path(s["path"])) for s in scan_configs],
        "nested_repos": nested_repos,
        "skills": {name: skill for name, skill in skill_map.items()},
        "skill_list": [skill["name"] for skill in all_skills],
        "duplicates": duplicates,
        "stats": {
            "total_skills": len(all_skills),
            "unique_skills": len(skill_map),
            "duplicates": len(duplicates),
            "with_git": sum(1 for s in all_skills if s["git"]["has_git"]),
            "without_git": sum(1 for s in all_skills if not s["git"]["has_git"]),
        },
    }

    # Track managed/unmanaged status per skill
    # A skill is "managed" if at least one location is a real dir under canonical library
    canonical_library = get_canonical_path()
    managed_count = 0
    unmanaged_count = 0
    for name, skill in skill_map.items():
        is_managed = False
        for loc in skill["locations"]:
            loc_path = Path(loc["real_path"])
            try:
                loc_path.relative_to(canonical_library)
                is_managed = True
                break
            except ValueError:
                continue
        skill["managed"] = is_managed
        if is_managed:
            managed_count += 1
        else:
            unmanaged_count += 1

    index["canonical_library"] = str(canonical_library)
    index["stats"]["managed"] = managed_count
    index["stats"]["unmanaged"] = unmanaged_count

    # Add freshness tracking (INDEX-03)
    index["scan_hash"] = hash_skill_files(all_skills)
    index["freshness"] = {
        "scan_time": index["scan_time"],
        "scan_hash": index["scan_hash"],
        "skill_count": len(all_skills),
    }

    return index

def install_from_github(
    repo_url: str,
    install_path: Path,
    *,
    depth: int = 1,
    reinstall: bool = False,
    backup_dir: Optional[Path] = None,
    gate_mode: str = "enforce",
    no_gate: bool = False,
    non_interactive: bool = False,
) -> int:
    """
    Clone a GitHub repo into the library, gated by validate + score.

    Clone always goes to a temp dir first; only moves to the library
    after gates pass (or are skipped).

    Args:
        repo_url: GitHub repository URL.
        install_path: Target library root.
        depth: Git clone depth.
        reinstall: Whether to allow overwriting an existing target.
        backup_dir: Backup directory for reinstall.
        gate_mode: "enforce" (run gates, abort on fail) or "skip".
        no_gate: Alias for gate_mode="skip".
        non_interactive: Auto-confirm after gates pass; fail if gates fail.

    Returns:
        Exit code: 0 = success, 1 = git/clone failure,
                  3 = user declined (interactive only),
                  4 = gate failure.
    """
    if no_gate:
        gate_mode = "skip"

    # Get repo name from URL
    clean_url = repo_url.rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]
    repo_name = clean_url.split("/")[-1]

    # Full install path (collision check target)
    target_path = install_path / repo_name

    # Collision check
    if target_path.exists() and any(target_path.iterdir()):
        if not reinstall:
            print(
                f"Path exists and is not empty: {target_path}. "
                f"Use --reinstall to overwrite.",
                file=sys.stderr,
            )
            return 1
        # --reinstall: clone fresh from remote to temp, gate the NEW content.
        # If gates pass -> backup old wrapper, remove it, move new clone into place.
        # If gates fail  -> temp discarded, old wrapper untouched (return 4).
        # This prevents malicious upstream content from bypassing gates.

    # ── Clone to temp dir ──────────────────────────────────────────────────────
    try:
        with tempfile.TemporaryDirectory(prefix="skillctl-install-") as tmp:
            tmp_repo_path = Path(tmp) / repo_name
            proc = subprocess.run(
                ["git", "clone", "--depth", str(depth), repo_url, str(tmp_repo_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                print(f"Clone failed: {proc.stderr.strip()}", file=sys.stderr)
                return 1

            # ── Gate evaluation (on the freshly-cloned content) ───────────────
            if gate_mode == "enforce":
                # Find all skill subdirs in the clone
                skill_dirs = []
                for item in tmp_repo_path.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        if (item / "SKILL.md").exists():
                            skill_dirs.append(item)
                        # Also check nested skills/ subdir pattern
                        skills_sub = item / "skills"
                        if skills_sub.is_dir():
                            for nested in skills_sub.iterdir():
                                if nested.is_dir() and (nested / "SKILL.md").exists():
                                    skill_dirs.append(nested)

                if not skill_dirs:
                    print(
                        f"No skills found in {repo_url} — still installing (repo may be empty)."
                    )
                else:
                    all_passed = True
                    for skill_dir in skill_dirs:
                        report = run_gates(skill_dir)
                        print(format_report(report))
                        if not report.gates_passed:
                            all_passed = False
                            print(
                                f"Gate failure for {skill_dir.name}. "
                                "Use --no-gate to override (not recommended)."
                            )

                    if not all_passed:
                        return 4  # gate failure

            # ── User confirmation ────────────────────────────────────────────
            if not should_prompt_user(non_interactive):
                pass  # auto-confirm
            else:
                print("\n[install] About to install the above skills. Ctrl-C to abort, Enter to confirm...")
                try:
                    input()
                except (KeyboardInterrupt, EOFError):
                    print("\nAborted.")
                    return 3

            # ── Install to library ─────────────────────────────────────────
            if target_path.exists():
                # Reinstall: backup old working tree, then refresh in-place.
                # NOTE: we do NOT shutil.rmtree the wrapper — that would lock on
                # .git/pack/* on Windows. Instead we git clean -fdx + git reset --hard
                # to replace working tree content while preserving .git/.
                backup = create_backup(
                    target_path,
                    install_path,
                    op_label=f"install-{repo_name}",
                    ignore_git=True,  # KEEP THIS — avoids Windows .git/pack file lock
                )
                print(f"[install] Backup: {backup}")
                # Refresh existing wrapper in-place (avoids Windows .git/ lock)
                try:
                    clean_proc = subprocess.run(
                        ["git", "-C", str(tmp_repo_path), "clean", "-fdx"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if clean_proc.returncode != 0:
                        print(f"git clean failed: {clean_proc.stderr.strip()}", file=sys.stderr)
                        return 1
                    fetch_proc = subprocess.run(
                        ["git", "-C", str(tmp_repo_path), "fetch", "--all", "--prune"],
                        capture_output=True, text=True, timeout=120,
                    )
                    if fetch_proc.returncode != 0:
                        print(f"git fetch failed: {fetch_proc.stderr.strip()}", file=sys.stderr)
                        return 1
                    reset_proc = subprocess.run(
                        ["git", "-C", str(tmp_repo_path), "reset", "--hard", "origin/HEAD"],
                        capture_output=True, text=True, timeout=120,
                    )
                    if reset_proc.returncode != 0:
                        print(f"git reset failed: {reset_proc.stderr.strip()}", file=sys.stderr)
                        return 1
                    # Now copy the refreshed content over the existing wrapper
                    # (the .git/ dir is preserved; only working tree files change)
                    for item in tmp_repo_path.iterdir():
                        if item.name == ".git":
                            continue
                        dst_item = target_path / item.name
                        if dst_item.exists():
                            if dst_item.is_dir():
                                shutil.rmtree(dst_item)
                            else:
                                dst_item.unlink()
                        if item.is_dir():
                            shutil.copytree(item, dst_item, symlinks=False)
                        else:
                            shutil.copy2(item, dst_item)
                    print(f"[install] Refreshed existing target: {target_path}")
                except subprocess.TimeoutExpired:
                    print("git operation timed out.", file=sys.stderr)
                    return 1
                except Exception as e:
                    meta = keep_backup(backup, reason=str(e))
                    print(f"[install] FAILED; backup retained at {meta['backup_path']}", file=sys.stderr)
                    raise
                else:
                    commit_backup(backup)
                    print("[install] backup auto-removed")
            else:
                shutil.move(str(tmp_repo_path), str(target_path))
                print(f"[install] Installed to: {target_path}")

            skills_detected = sum(1 for _ in target_path.rglob("SKILL.md"))
            if skills_detected:
                print(f"  Detected {skills_detected} SKILL.md file(s).")
            return 0

    except subprocess.TimeoutExpired:
        print("Clone timed out.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Install failed: {e}", file=sys.stderr)
        return 1

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime and date objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)

def save_index(index: dict, output_path: Path):
    """Save index to JSON file."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
    print(f"\nIndex saved to: {output_path}")
    print(
        f"Total: {index['stats']['total_skills']} skills, {index['stats']['duplicates']} duplicates"
    )

def load_config(config_path: Path) -> dict:
    """Load scan configuration from YAML file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - Scan, Index, and Install Skills"
    )
    parser.add_argument("--config", "-c", type=str, help="Path to scan-config.yaml")
    parser.add_argument(
        "--output", "-o", type=str, default="index.json", help="Output index file path"
    )
    parser.add_argument(
        "--paths",
        "-p",
        type=str,
        nargs="+",
        help="Direct paths to scan (format: path:scope:priority)",
    )
    parser.add_argument(
        "--path",
        type=str,
        help="Scan a single project path (for project-level skills, e.g., E:\\projects\\myapp\\.claude\\skills)",
    )
    parser.add_argument(
        "--install", "-i", type=str, help="Install a skill from GitHub URL"
    )
    parser.add_argument(
        "--reinstall",
        action="store_true",
        help="Overwrite existing install path (backup auto-managed by _lib.backup; auto-removed on success, retained on failure)",
    )
    parser.add_argument(
        "--no-auto-nested",
        action="store_true",
        help="Disable auto-detection of nested skills",
    )
    parser.add_argument(
        "--track-freshness",
        action="store_true",
        default=True,
        help="Track skill file hash for freshness detection (default: true)",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="After scan, infer github_url for orphan skills via GitHub API. "
             "WARNING: makes network requests (default: off)",
    )
    parser.add_argument(
        "--gate-mode",
        choices=["enforce", "skip"],
        default="enforce",
        help="Gate enforcement mode (default: enforce). "
             "'skip' bypasses validate+score gates (not recommended).",
    )
    parser.add_argument(
        "--no-gate",
        action="store_true",
        help="Skip validate and score gates entirely. WARN: bypasses safety checks.",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Auto-confirm after gates pass; fail if gates fail. For CI/agents.",
    )

    args = parser.parse_args()

    # Handle install command
    if args.install:
        # Determine canonical path for installation
        config_path = Path(args.config) if args.config else None
        canonical = get_canonical_path(config_path)

        # Install path is the canonical library path
        install_path = canonical
        print(f"Installing to canonical path: {install_path}")

        exit_code = install_from_github(
            args.install,
            install_path,
            reinstall=args.reinstall,
            gate_mode=args.gate_mode,
            no_gate=args.no_gate,
            non_interactive=args.non_interactive,
        )
        if exit_code == 0:
            print("  Run 'skillctl scan' to refresh index.json with the new skills.")
        return exit_code

    # Determine scan paths
    auto_detect_nested = not args.no_auto_nested

    if args.path:
        # SCAN-01: Single project path scanning for project-level skills
        project_path = expand_path(args.path)
        if not project_path.exists():
            print(f"Error: Path does not exist: {project_path}")
            return 1
        scan_paths = [
            {
                "path": str(project_path),
                "scope": "project",
                "priority": "high",
            }
        ]
        print(f"Scanning project-level skills from: {project_path}")
    elif args.config and Path(args.config).exists():
        config = load_config(Path(args.config))
        scan_paths = config.get("scan_paths", [])
    elif args.paths:
        scan_paths = []
        for p in args.paths:
            parts = p.split(":")
            # Handle Windows drive letters: E:\path → E:\path
            if len(parts) >= 2 and len(parts[0]) == 1 and parts[1].startswith("\\"):
                path = parts[0] + ":" + parts[1]
                scope = parts[2] if len(parts) > 2 else "global"
                priority = parts[3] if len(parts) > 3 else "medium"
            else:
                path = parts[0]
                scope = parts[1] if len(parts) > 1 else "global"
                priority = parts[2] if len(parts) > 2 else "medium"
            scan_paths.append(
                {
                    "path": path,
                    "scope": scope,
                    "priority": priority,
                }
            )
    else:
        # Default paths
        home = Path.home()
        scan_paths = [
            {
                "path": str(home / ".claude" / "skills"),
                "scope": "global",
                "priority": "high",
            },
        ]

    # Build index
    index = build_index(scan_paths, auto_detect_nested=auto_detect_nested)

    # Enrichment: only runs when --enrich is set (zero network by default)
    if args.enrich:
        print("\n=== Enrichment (--enrich) ===")
        skills = index.get("skills", {})
        enriched = 0
        rate_remaining = 999
        rate_reset = 0
        for skill_name, skill_data in skills.items():
            meta = skill_data.get("metadata", {})
            if meta.get("github_url"):
                continue  # Already has github_url, skip
            # Find the first real path for this skill
            locations = skill_data.get("locations", [])
            real_loc = next(
                (l for l in locations if not l.get("is_symlink")),
                locations[0] if locations else None,
            )
            if not real_loc:
                continue
            skill_dir = Path(real_loc["real_path"])
            if not skill_dir.exists():
                continue
            inferred_url, method, confidence = infer_github_url(
                skill_name, skill_dir, rate_remaining, rate_reset
            )
            if inferred_url:
                # Update the in-memory index (do NOT write to SKILL.md)
                if "github_url" not in meta:
                    meta["github_url"] = inferred_url
                    meta["_enrichment"] = {"method": method, "confidence": confidence}
                    skill_data["metadata"] = meta
                    enriched += 1
                    print(f"  [enriched] {skill_name}: {inferred_url} ({method}, {confidence:.0%})")
        if enriched > 0:
            print(f"\nEnrichment found {enriched} URLs — index will reflect inferred values.")
        else:
            print("  No enrichment opportunities found.")

    # Save
    output_path = Path(args.output)
    save_index(index, output_path)

    # Print summary
    print("\n=== Scan Summary ===")
    print(f"Total skills: {index['stats']['total_skills']}")
    print(f"Unique skills: {index['stats']['unique_skills']}")
    print(f"With git: {index['stats']['with_git']}")
    print(f"Without git: {index['stats']['without_git']}")

    if index.get("nested_repos"):
        print(f"\nNested Git repos detected: {len(index['nested_repos'])}")
        for repo in index["nested_repos"]:
            print(f"  - {repo['repo_path']} (skills in {repo['skills_path']})")

    if index["duplicates"]:
        print(f"\nDuplicates found: {len(index['duplicates'])}")
        for dup in index["duplicates"]:
            print(f"  - {dup['name']}: {len(dup['instances'])} instances")

    return 0

if __name__ == "__main__":
    sys.exit(main())
