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
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict
import argparse
import urllib.request

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def get_canonical_path(config_path: Path = None) -> Path:
    """
    Get the canonical skill library path.

    Priority:
    1. SKILL_LIBRARY_PATH environment variable
    2. .canonical_path file in skillctl directory
    3. canonical_path in scan-config.yaml
    4. Default: E:\\Desktop\\Skills
    """
    # 1. Environment variable (highest priority)
    env_path = os.environ.get("SKILL_LIBRARY_PATH")
    if env_path:
        path = expand_path(env_path)
        if path.exists() or path.parent.exists():
            print(f"Using canonical path from SKILL_LIBRARY_PATH: {path}")
            return path

    skillctl_dir = Path(__file__).parent.parent

    # 2. .canonical_path file
    canonical_file = skillctl_dir / ".canonical_path"
    if canonical_file.exists():
        try:
            lines = canonical_file.read_text().splitlines()
            # Skip blank lines and comment lines
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

    # 3. Config file
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

    # 4. Default
    default_path = Path("E:\\Desktop\\Skills")
    print(f"Using default canonical path: {default_path}")
    return default_path


def is_symlink(path: Path) -> bool:
    r"""
    Check if path is a symlink, junction point, or has a symlink in its parent chain.

    A path like C:\Users\.claude\skills\ljg-skills\skills\ljg-card
    is effectively a symlink if any ancestor in its parent chain is a symlink.
    """
    try:
        # First check if the path itself is a symlink
        if path.is_symlink():
            return True

        # Check parent chain - if any parent is a symlink, this path is also "under" a symlink
        current = path.parent
        while current != current.parent:  # Walk up to root
            try:
                if current.is_symlink():
                    return True
                # On Windows, also check for junction points
                if os.name == 'nt':
                    try:
                        resolved = current.resolve()
                        if resolved != current and current.is_dir():
                            return True
                    except (OSError, RuntimeError):
                        pass
            except OSError:
                break
            current = current.parent

        # On Windows, check if the path itself is a junction
        if os.name == 'nt':
            try:
                resolved = path.resolve()
                if resolved != path and path.is_dir():
                    return True
            except (OSError, RuntimeError):
                pass

        return False
    except OSError:
        return False


def resolve_symlink_target(path: Path) -> Path:
    r"""
    Resolve symlink, junction, or regular path to real path.
    ALWAYS resolves to get the true physical path, even for non-symlink paths.
    This ensures that paths like E:\Skills\ljg-skills\skills\ljg-card
    resolve correctly even when ljg-card itself is not a symlink.
    """
    try:
        return path.resolve()
    except OSError:
        return path


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
    """Fetch GitHub repo info (from fetch_github_info.py logic)."""
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
    depth: int = 1,
    reinstall: bool = False,
    backup_dir: Optional[Path] = None,
) -> dict:
    """
    Clone a GitHub repo to install_path as a parent wrapper.

    The repo is cloned to <install_path>/<repo_name>/ with .git history
    preserved, so the user can `git pull` later for updates.

    Returns dict with:
    - success: bool
    - path: installed parent wrapper path
    - error: error message if failed
    - skills_detected: count of SKILL.md files inside the wrapper
    - reinstalled: bool (True if existing dir was wiped and re-cloned)
    - backup: backup path if reinstall wiped data
    """
    result = {
        "success": False,
        "path": str(install_path),
        "error": None,
        "skills_detected": 0,
        "reinstalled": False,
        "backup": None,
    }

    # Get repo name from URL
    clean_url = repo_url.rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]
    repo_name = clean_url.split("/")[-1]

    # Full install path
    target_path = install_path / repo_name

    # Collision detection: refuse / backup-and-overwrite
    if target_path.exists() and any(target_path.iterdir()):
        if not reinstall:
            result["error"] = (
                f"Path exists and is not empty: {target_path}. "
                f"Use --reinstall to overwrite (backs up to .skillctl-backup/)."
            )
            return result
        # --reinstall path: backup working tree (skip .git/), then
        # in-place refresh via `git fetch && git reset --hard origin/HEAD`.
        # This avoids Windows file-lock issues when deleting .git/objects/pack/*.
        if backup_dir is None:
            backup_dir = install_path / ".skillctl-backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{repo_name}_{timestamp}"
        try:
            shutil.copytree(
                target_path,
                backup_path,
                symlinks=False,
                ignore=shutil.ignore_patterns(".git"),
            )
            result["backup"] = str(backup_path)
        except Exception as e:
            result["error"] = f"Backup failed: {e}"
            return result

        # In-place refresh instead of rmtree + clone (Windows-friendly)
        try:
            fetch_proc = subprocess.run(
                ["git", "-C", str(target_path), "fetch", "--all", "--prune"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if fetch_proc.returncode != 0:
                result["error"] = f"git fetch failed: {fetch_proc.stderr.strip()}"
                return result
            reset_proc = subprocess.run(
                ["git", "-C", str(target_path), "reset", "--hard", "origin/HEAD"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if reset_proc.returncode != 0:
                result["error"] = f"git reset failed: {reset_proc.stderr.strip()}"
                return result
            result["reinstalled"] = True
        except subprocess.TimeoutExpired:
            result["error"] = "git fetch/reset timed out"
            return result
        except Exception as e:
            result["error"] = f"Reinstall refresh failed: {e}"
            return result

        # Count skills after refresh (informational)
        try:
            result["skills_detected"] = sum(1 for _ in target_path.rglob("SKILL.md"))
        except Exception:
            pass

        result["success"] = True
        result["path"] = str(target_path)
        return result

    try:
        # Clone with depth=1 for efficiency
        proc = subprocess.run(
            ["git", "clone", "--depth", str(depth), repo_url, str(target_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            result["error"] = proc.stderr
            return result

        result["success"] = True
        result["path"] = str(target_path)

        # Count SKILL.md files in the wrapper (informational only;
        # the post-install 'skillctl scan' is what populates index.json)
        try:
            result["skills_detected"] = sum(1 for _ in target_path.rglob("SKILL.md"))
        except Exception:
            pass

    except subprocess.TimeoutExpired:
        result["error"] = "Clone timed out"
    except Exception as e:
        result["error"] = str(e)

    return result


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
        help="Overwrite existing install path (backs up to <library>/.skillctl-backup/<ts>/<repo>/)",
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

    args = parser.parse_args()

    # Handle install command
    if args.install:
        # Determine canonical path for installation
        config_path = Path(args.config) if args.config else None
        canonical = get_canonical_path(config_path)

        # Install path is the canonical library path
        install_path = canonical
        print(f"Installing to canonical path: {install_path}")

        result = install_from_github(args.install, install_path, reinstall=args.reinstall)
        if result["success"]:
            print(f"✓ Installed to: {result['path']}")
            if result["skills_detected"]:
                print(
                    f"  Detected {result['skills_detected']} SKILL.md file(s) inside the wrapper."
                )
            if result.get("backup"):
                print(f"  Previous content backed up to: {result['backup']}")
            print("  Run 'skillctl scan' to refresh index.json with the new skills.")
        else:
            print(f"✗ Install failed: {result['error']}")
            return 1
        # After install, re-scan
        args.no_auto_nested = True  # Don't auto-detect on fresh install

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
