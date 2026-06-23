#!/usr/bin/env python3
"""
Skill Manager - List Skills Module

List skills from index or by scanning directories.
Supports:
- Index-based listing (fast, no rescan)
- Directory scanning (for finding new skills)

Usage:
    python list_skills.py --index skillctl/index.json
    python list_skills.py --path ~/.claude/skills
    python list_skills.py --index skillctl/index.json --filter skill-name
"""

import os
import sys
import json
import yaml
from pathlib import Path
from typing import Optional, List, Dict
import argparse

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


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
            "version": frontmatter.get("version", "0.1.0"),
            "scope": frontmatter.get("scope", "project"),
        }
    except Exception as e:
        return None


def find_skill_md_files(root_path: Path) -> List[Path]:
    """Find all SKILL.md files under root_path."""
    skill_files = []

    # Direct skills at root level
    for item in root_path.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                skill_files.append(skill_md)

    return skill_files


def scan_directory(scan_path: Path) -> List[dict]:
    """Scan a directory for skills (fallback when no index)."""
    skills = []

    if not scan_path.exists():
        print(f"Warning: Path does not exist: {scan_path}", file=sys.stderr)
        return skills

    skill_files = find_skill_md_files(scan_path)

    for skill_md in skill_files:
        skill_dir = skill_md.parent
        metadata = parse_skill_md(skill_md)
        if not metadata:
            continue

        skills.append({
            "name": metadata.get("name", skill_dir.name),
            "path": str(skill_dir),
            "description": metadata.get("description", ""),
            "version": metadata.get("version", "0.1.0"),
            "scope": metadata.get("scope", "project"),
        })

    return skills


def list_from_index(index_path: Path, filter_name: Optional[str] = None) -> List[dict]:
    """
    List skills from index.json (fast path, no rescan).

    Args:
        index_path: Path to index.json
        filter_name: Optional skill name filter

    Returns:
        List of skill info dicts
    """
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    skills = []
    skills_data = index.get("skills", {})

    for name, skill_info in skills_data.items():
        if filter_name and filter_name.lower() not in name.lower():
            continue

        # Get primary location
        locations = skill_info.get("locations", [])
        primary_path = locations[0]["path"] if locations else ""

        # Get git info
        git_info = skill_info.get("git", {})

        skills.append({
            "name": name,
            "path": primary_path,
            "description": skill_info.get("metadata", {}).get("description", ""),
            "version": skill_info.get("metadata", {}).get("version", "0.1.0"),
            "scope": skill_info.get("metadata", {}).get("scope", "project"),
            "has_git": git_info.get("has_git", False),
            "is_symlink": locations[0].get("is_symlink", False) if locations else False,
        })

    return skills


def format_skill_row(skill: dict, max_width: int = 100) -> str:
    """Format a skill as a table row."""
    name = skill["name"][:20].ljust(20)
    version = skill.get("version", "0.1.0")[:8].ljust(8)
    scope = skill.get("scope", "project")[:10].ljust(10)
    description = skill.get("description", "")[:max_width - 50]

    flags = []
    if skill.get("has_git"):
        flags.append("git")
    if skill.get("is_symlink"):
        flags.append("link")
    flag_str = f"[{','.join(flags)}]" if flags else ""

    return f"{name} | {version} | {scope} | {description} {flag_str}"


# Category definitions for skill map
CATEGORIES = {
    "认知原子": {
        "icon": "◆",
        "keywords": ["plain", "word", "writes", "paper", "learn", "plain", "grok", "explain", "understand"],
        "description": "内容处理的原子操作"
    },
    "输出铸造": {
        "icon": "▲",
        "keywords": ["card", "cast", "image", "visual", "png", "pdf", "docx", "xlsx", "pptx", "slide", "deck"],
        "description": "将内容转化为可交付物"
    },
    "联网触达": {
        "icon": "●",
        "keywords": ["reach", "social", "twitter", "x.com", "weibo", "bilibili", "search", "fetch", "crawl"],
        "description": "与外部世界交互"
    },
    "系统运维": {
        "icon": "■",
        "keywords": ["skill", "manage", "update", "install", "ctl", "system", "health", "check", "monitor"],
        "description": "Agent 自身的维护和管理"
    },
    "环境部署": {
        "icon": "★",
        "keywords": ["deploy", "install", "setup", "init", "config", "setup"],
        "description": "一次性安装和配置"
    },
    "飞书集成": {
        "icon": "✈",
        "keywords": ["lark", "feishu", "飞书"],
        "description": "飞书平台集成"
    },
    "学习研究": {
        "icon": "◎",
        "keywords": ["research", "paper", "learn", "study", "analysis", "review", "deep"],
        "description": "学习和研究工具"
    }
}


def classify_skill(skill: dict) -> str:
    """Classify a skill into a category based on name and description."""
    name = skill.get("name", "").lower()
    desc = skill.get("description", "").lower()

    for category, info in CATEGORIES.items():
        for keyword in info["keywords"]:
            if keyword in name or keyword in desc:
                return category

    return "其他"


def print_skill_map(skills: List[dict]):
    """Print skills in ASCII skill map format."""
    # Classify skills
    categorized = {cat: [] for cat in CATEGORIES}
    categorized["其他"] = []
    uncategorized = []

    for skill in skills:
        cat = classify_skill(skill)
        categorized[cat].append(skill)

    # Count totals
    total = len(skills)
    invocable = sum(1 for s in skills if s.get("user_invocable"))
    categorized_count = sum(1 for cat in categorized for _ in categorized[cat])

    # Print header
    print(f"\n╔{'═' * 66}╗")
    print(f"║{' SKILL MAP ':^66}║")
    print(f"╠{'═' * 66}╣")

    # Print each category
    for cat_name, cat_info in CATEGORIES.items():
        cat_skills = categorized.get(cat_name, [])
        if not cat_skills:
            continue

        print(f"║ {cat_info['icon']} {cat_name} {'─' * (60 - len(cat_name))}║")

        for skill in sorted(cat_skills, key=lambda s: s["name"]):
            name = skill["name"][:18]
            version = skill.get("version", "0.1.0")[:6]
            desc = skill.get("description", "")[:35].replace("\n", " ").strip()
            invocable_mark = "/" if skill.get("user_invocable") else ""

            print(f"║   {name:<18} v{version:<6} {desc:<35} {invocable_mark}  ║")

    # Print uncategorized
    other_skills = categorized.get("其他", [])
    if other_skills:
        print(f"║ ◎ 其他技能 {'─' * 56}║")
        for skill in sorted(other_skills, key=lambda s: s["name"])[:10]:
            name = skill["name"][:18]
            version = skill.get("version", "0.1.0")[:6]
            desc = skill.get("description", "")[:35].replace("\n", " ").strip()
            invocable_mark = "/" if skill.get("user_invocable") else ""
            print(f"║   {name:<18} v{version:<6} {desc:<35} {invocable_mark}  ║")
        if len(other_skills) > 10:
            print(f"║   ... 还有 {len(other_skills) - 10} 个未分类技能{' ' * 27}║")

    # Print footer with stats
    print(f"╠{'═' * 66}╣")
    print(f"║ 总计: {total} skills | 可直接调用: {invocable} | 分类: {categorized_count}        ║")
    print(f"╚{'═' * 66}╝")

    # Print legend
    print("\n图标: ", end="")
    for cat_info in CATEGORIES.values():
        print(f"{cat_info['icon']}={cat_info['description'][:4]}, ", end="")
    print(f"/ = 可直接调用")


def print_skill_table(skills: List[dict]):
    """Print skills in table format."""
    header = f"{'Name':<20} | {'Ver':<8} | {'Scope':<10} | {'Description':<50}"
    print(header)
    print("-" * len(header))

    for skill in sorted(skills, key=lambda s: s["name"]):
        print(format_skill_row(skill))


def print_index_info(index_path: Path):
    """Print index file information."""
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)

        print(f"\nIndex: {index_path}")
        print(f"  Version: {index.get('version', 'unknown')}")
        print(f"  Scan time: {index.get('scan_time', 'unknown')}")
        print(f"  Skills: {index.get('stats', {}).get('total_skills', 'unknown')}")

        freshness = index.get("freshness", {})
        if freshness:
            print(f"  Freshness hash: {freshness.get('scan_hash', 'unknown')}")
            print(f"  Skill count: {freshness.get('skill_count', 'unknown')}")

    except Exception as e:
        print(f"Warning: Could not read index info: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - List skills from index or directory"
    )
    parser.add_argument(
        "--index", "-i", type=str,
        help="Path to index.json (fast path, uses existing index)"
    )
    parser.add_argument(
        "--path", "-p", type=str,
        help="Path to scan (slow path, rescans directory)"
    )
    parser.add_argument(
        "--filter", "-f", type=str,
        help="Filter skills by name (case-insensitive substring match)"
    )
    parser.add_argument(
        "--info", action="store_true",
        help="Show index file information"
    )
    parser.add_argument(
        "--map", "-m", action="store_true",
        help="Show skill map (ASCII visualization)"
    )

    args = parser.parse_args()

    # If index provided, use fast path
    if args.index:
        index_path = expand_path(args.index)
        if not index_path.exists():
            print(f"Error: Index file not found: {index_path}")
            return 1

        if args.info:
            print_index_info(index_path)

        skills = list_from_index(index_path, args.filter)
        print(f"\nFound {len(skills)} skills in index")
        if args.map:
            print_skill_map(skills)
        else:
            print_skill_table(skills)

        return 0

    # If path provided, use slow path (scan directory)
    if args.path:
        scan_path = expand_path(args.path)
        skills = scan_directory(scan_path)
        print(f"\nScanned {scan_path}")
        print(f"Found {len(skills)} skills")
        if args.map:
            print_skill_map(skills)
        else:
            print_skill_table(skills)
        return 0

    # No index or path provided - show help
    parser.print_help()
    print("\nExamples:")
    print("  python list_skills.py --index skillctl/index.json")
    print("  python list_skills.py --index skillctl/index.json --filter lark")
    print("  python list_skills.py --path ~/.claude/skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
