#!/usr/bin/env python3
"""
GitHub Repository Info Fetcher

Fetches repository information using git ls-remote and direct HTTP requests.
Used by skill-manager for GitHub-based skill installation and update detection.
"""

import sys
import json
import subprocess
import urllib.request
from typing import Optional


def get_repo_info(url: str) -> dict:
    """
    Fetches repository information.

    Returns a dictionary with:
    - name: repository name
    - url: original URL
    - latest_hash: HEAD commit hash
    - readme: README.md content (truncated)
    """
    # Normalize URL (remove .git suffix if present)
    clean_url = url.rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]

    repo_name = clean_url.split("/")[-1]

    # 1. Get Latest Commit Hash (using git ls-remote to avoid full clone)
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
    except Exception as e:
        print(f"Warning: Could not fetch git hash for {url}: {e}", file=sys.stderr)

    # 2. Fetch README (Try main, then master)
    readme_content = ""
    readme_url_base = clean_url.replace("github.com", "raw.githubusercontent.com")

    for branch in ["main", "master"]:
        try:
            readme_url = f"{readme_url_base}/{branch}/README.md"
            with urllib.request.urlopen(readme_url, timeout=10) as response:
                readme_content = response.read().decode("utf-8")
                break
        except Exception:
            continue

    if not readme_content:
        # Try lowercase readme
        for branch in ["main", "master"]:
            try:
                readme_url = f"{readme_url_base}/{branch}/readme.md"
                with urllib.request.urlopen(readme_url, timeout=10) as response:
                    readme_content = response.read().decode("utf-8")
                    break
            except Exception:
                continue

    return {
        "name": repo_name,
        "url": url,
        "latest_hash": latest_hash,
        "readme": readme_content[:10000],  # Truncate if too huge
    }


def check_remote_updates(local_hash: str, repo_url: str) -> dict:
    """
    Check if a remote repo has updates compared to local hash.

    Returns dict with:
    - has_update: bool
    - remote_hash: str
    - commits_behind: int (if has_update)
    """
    result = {"has_update": False, "remote_hash": "unknown", "commits_behind": 0}

    try:
        proc = subprocess.run(
            ["git", "ls-remote", repo_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout:
            remote_hash = proc.stdout.split()[0]
            result["remote_hash"] = remote_hash
            result["has_update"] = remote_hash != local_hash
    except Exception:
        pass

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fetch_github_info.py <github_url>")
        sys.exit(1)

    url = sys.argv[1]
    info = get_repo_info(url)
    print(json.dumps(info, indent=2))
