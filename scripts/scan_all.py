#!/usr/bin/env python3
"""
scan_all.py — Comprehensive Skill Scanner

Scans ALL skill roots (global + project-level), infers github_url
for orphan skills via multiple strategies, and returns a unified JSON report.

Usage:
    python scan_all.py [skill_root [skill_root ...]]
    python scan_all.py --enrich [skill_root ...]  # Also attempt enrichment

Strategies for github_url inference:
1. Already has github_url in frontmatter → use it
2. Known patterns: skill-name matches known repo patterns
3. GitHub API search: query "SKILL.md + skill_name"
4. git remote: if skill dir is a git repo, get remote origin
5. Mark as "orphan" if no source found

Exit codes:
    0 = success (results printed)
    1 = partial (some skills had errors)
    2 = usage error
"""

import os
import sys
import json
import yaml
import argparse
import subprocess
import time
import re
from pathlib import Path
from urllib.parse import quote_plus

# ─── GitHub API ───────────────────────────────────────────────────────────────

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
            # Check rate limit
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
    import time

    if reset_ts > 0:
        wait_sec = reset_ts - time.time()
        if wait_sec > 0:
            print(f"[Rate limited] Waiting {int(wait_sec) + 5}s...", file=sys.stderr)
            time.sleep(wait_sec + 5)


# ─── GitHub URL Inference ─────────────────────────────────────────────────────

# Known patterns: (skill_prefix, search_query_suffix, confidence)
# confidence: 1.0 = direct match, 0.7 = likely match
KNOWN_PATTERNS = [
    # Well-known single-repo skills
    ("agent-reach", "agent-reach/agent-reach", 1.0),
    ("x-tweet-fetcher", "skillcoder/x-tweet-fetcher", 0.8),
    ("last30days", "skillcoder/last30days", 0.8),
    # ljg-* series (likely from ljg-*/skills repos)
    # money-* series (likely from money-* sub-modules)
    # baoyu-* series (likely from baoyu-* sub-modules)
]

# Known org prefixes and their GitHub org/repo patterns
PREFIX_ORG_MAP = {
    "baoyu": None,  # Search needed
    "ljg": None,  # Search needed
    "money": None,  # Search needed
    "yao": "yao",
}


def infer_github_url(skill_name, skill_dir, rate_remaining, rate_reset):
    """
    Try to infer the GitHub URL for an orphan skill.
    Returns (url, method, confidence) or (None, None, 0).
    """
    # 1. Check known patterns
    for prefix, known_url, conf in KNOWN_PATTERNS:
        if skill_name.startswith(prefix):
            return f"https://github.com/{known_url}", f"known_pattern:{prefix}", conf

    # 2. Try git remote if skill dir is a git repo
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=skill_dir,
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
        # First try exact name match via repo search
        search_url = f"/search/code?q={quote_plus(query)}&per_page=5"
        data, remaining, reset = github_api_get(search_url)
        new_remaining = min(rate_remaining, remaining)
        wait_for_rate_limit(reset)

        if data and "items" in data and len(data["items"]) > 0:
            # Get the repo full_name from the first item
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


# ─── Skill Scanning ────────────────────────────────────────────────────────────

DEFAULT_SKILL_ROOTS = [
    os.path.expanduser(r"~/.claude/skills"),
]

SKILL_MD_NAME = "SKILL.md"


def parse_frontmatter(skill_md_path):
    """Parse YAML frontmatter from SKILL.md. Returns (metadata_dict, full_content)."""
    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---")
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            return meta, content
        return {}, content
    except Exception:
        return {}, ""


def get_git_hash(skill_dir):
    """Try to get current git commit hash for a skill directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=skill_dir,
            capture_output=True,
            text=True,
            timeout=5,
            windowsHide=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except Exception:
        pass
    return None


def get_remote_hash(github_url):
    """Get latest commit hash from remote via git ls-remote."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", github_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            windowsHide=True,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.split()[0]
    except Exception:
        pass
    return None


def scan_skill_dir(skill_dir, rate_remaining=999, rate_reset=0):
    """
    Scan a single skill directory.
    Returns a dict with skill info or None if not a valid skill.
    """
    skill_md = os.path.join(skill_dir, SKILL_MD_NAME)
    if not os.path.isfile(skill_md):
        return None

    meta, content = parse_frontmatter(skill_md)
    name = meta.get("name", os.path.basename(skill_dir))
    description = meta.get("description", "")
    version = str(meta.get("version", "0.0.0"))
    github_url = meta.get("github_url", None)
    local_hash = meta.get("github_hash", None)
    skill_type = "GitHub" if github_url else "Standard"

    result = {
        "name": name,
        "dir": skill_dir,
        "type": skill_type,
        "version": version,
        "description": description[:80] if description else "",
        "github_url": github_url,
        "local_hash": local_hash,
        "remote_hash": None,
        "status": "unknown",
        "enrichment_needed": False,
        "enrichment_method": None,
        "enrichment_confidence": 0.0,
    }

    # If it has github_url, get remote hash and check status
    if github_url:
        remote_hash = get_remote_hash(github_url)
        result["remote_hash"] = remote_hash
        if not remote_hash:
            result["status"] = "error"
            result["message"] = "Could not reach remote"
        elif local_hash and local_hash != remote_hash:
            result["status"] = "outdated"
            result["message"] = "Updates available"
        elif local_hash == remote_hash:
            result["status"] = "current"
            result["message"] = "Up to date"
        else:
            result["status"] = "unknown"
            result["message"] = "No local hash recorded"
    else:
        # Orphan skill — try to infer github_url
        result["enrichment_needed"] = True
        inferred_url, method, confidence = infer_github_url(
            name, skill_dir, rate_remaining, rate_reset
        )
        result["enrichment_url"] = inferred_url
        result["enrichment_method"] = method
        result["enrichment_confidence"] = confidence
        if inferred_url:
            result["status"] = "enrichable"
            result["message"] = f"Can enrich via {method} ({confidence:.0%})"
        else:
            result["status"] = "orphan"
            result["message"] = "No GitHub source found"

    return result


def scan_all_skills(skill_roots, enrich=False):
    """Scan all skills across all roots."""
    all_skills = []
    errors = []

    # First pass: collect all orphan skills and rate limit info
    rate_remaining = 999
    rate_reset = 0

    for root in skill_roots:
        if not os.path.isdir(root):
            errors.append(f"Skipping (not found): {root}")
            continue

        for item in os.listdir(root):
            skill_dir = os.path.join(root, item)
            if not os.path.isdir(skill_dir):
                continue

            result = scan_skill_dir(skill_dir, rate_remaining, rate_reset)
            if result:
                all_skills.append(result)
            else:
                # Not a valid skill dir (no SKILL.md)
                pass

    return all_skills, errors


def generate_report(all_skills, errors):
    """Generate a structured report from scan results."""
    total = len(all_skills)
    github_managed = [s for s in all_skills if s["type"] == "GitHub"]
    orphan = [s for s in all_skills if s["type"] == "Standard"]
    current = [s for s in all_skills if s["status"] == "current"]
    outdated = [s for s in all_skills if s["status"] == "outdated"]
    enrichable = [s for s in all_skills if s["status"] == "enrichable"]
    truly_orphan = [s for s in all_skills if s["status"] == "orphan"]
    error_skills = [s for s in all_skills if s["status"] == "error"]

    report = {
        "summary": {
            "total_skills": total,
            "github_managed": len(github_managed),
            "orphan_standard": len(orphan),
            "current": len(current),
            "outdated": len(outdated),
            "enrichable": len(enrichable),
            "truly_orphan": len(truly_orphan),
            "errors": len(error_skills),
        },
        "errors": errors,
        "skills": all_skills,
    }

    return report


def print_report(report):
    """Pretty-print the report to stdout."""
    s = report["summary"]

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              SKILL INVENTORY REPORT                         ║
╠══════════════════════════════════════════════════════════════╣
║  Total Skills           : {s["total_skills"]:>5}
║  ├─ GitHub Managed      : {s["github_managed"]:>5}   (has github_url)
║  └─ Standard/Orphan    : {s["orphan_standard"]:>5}   (no github_url)
║  Update Status                                               ║
║  ├─ Current            : {s["current"]:>5}
║  ├─ Outdated          : {s["outdated"]:>5}
║  ├─ Enrichable        : {s["enrichable"]:>5}   (can infer URL)
║  ├─ Truly Orphan       : {s["truly_orphan"]:>5}   (no source found)
║  └─ Errors            : {s["errors"]:>5}
╚══════════════════════════════════════════════════════════════╝
""")

    # ── Outdated ──────────────────────────────────────────────
    outdated = [s for s in report["skills"] if s["status"] == "outdated"]
    if outdated:
        print("┌─ OUTDATED ────────────────────────────────────────────────")
        for s in outdated:
            print(f"│  ● {s['name']} ({s['local_hash'][:7]} → {s['remote_hash'][:7]})")
        print("└─────────────────────────────────────────────────────────")

    # ── Enrichable ──────────────────────────────────────────
    enrichable = [s for s in report["skills"] if s["status"] == "enrichable"]
    if enrichable:
        print("┌─ ENRICHABLE ────────────────────────────────────────────")
        for s in sorted(enrichable, key=lambda x: -x["enrichment_confidence"]):
            print(
                f"│  ○ {s['name']:<30} | {s['enrichment_method']:<25} | {s['enrichment_confidence']:.0%}"
            )
        print("└─────────────────────────────────────────────────────────")

    # ── Truly Orphan ─────────────────────────────────────────
    orphan = [s for s in report["skills"] if s["status"] == "orphan"]
    if orphan:
        print("┌─ ORPHAN (no GitHub source found) ──────────────────────")
        for s in orphan:
            print(f"│  ? {s['name']:<30} | {s['description'][:40]}")
        print("└─────────────────────────────────────────────────────────")

    if report["errors"]:
        print("┌─ ERRORS ────────────────────────────────────────────────")
        for e in report["errors"]:
            print(f"│  ! {e}")
        print("└─────────────────────────────────────────────────────────")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Comprehensive skill scanner with GitHub URL inference."
    )
    parser.add_argument(
        "roots",
        nargs="*",
        default=DEFAULT_SKILL_ROOTS,
        help="Skill directories to scan (default: all known locations)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of human-readable report",
    )
    parser.add_argument(
        "--enrich", action="store_true", help="Also print enrichment commands"
    )
    parser.add_argument(
        "--github-token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub token for API (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[], help="Skill names to exclude"
    )

    args = parser.parse_args()

    if args.github_token:
        GITHUB_TOKEN = args.github_token

    all_skills, errors = scan_all_skills(args.roots)

    # Filter excluded
    if args.exclude:
        all_skills = [s for s in all_skills if s["name"] not in args.exclude]

    report = generate_report(all_skills, errors)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)

        if args.enrich:
            enrichable = [s for s in report["skills"] if s["status"] == "enrichable"]
            if enrichable:
                print("── ENRICHMENT COMMANDS ─────────────────────────────────────")
                for s in enrichable:
                    if s["enrichment_confidence"] >= 0.75:
                        print(
                            f'  python scripts/enrich_skill.py "{s["dir"]}" --url "{s["enrichment_url"]}" --confirm'
                        )
                print()
