#!/usr/bin/env python3
"""
Skill Scoring Module - 8-Dimension Evaluation Engine

Standalone CLI tool for scoring skills using darwin-skill's 8-dimension rubric (100pt).
Decoupled from scan_and_index.py for independent operation.

Usage:
    python score.py --skill <name>      Score single skill
    python score.py --cluster <name>    Score all skills in cluster
    python score.py --all               Score all skills
    python score.py --report --cluster <name>  Generate markdown report
"""

import os
import sys
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import argparse

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Base paths — resolved at import time from env > user.json.
# Never hardcode a path: each operator's library is different.
from user_config import resolve_library_path
_BASE_DIR_RESOLVED = resolve_library_path()
if _BASE_DIR_RESOLVED is None:
    raise SystemExit(
        "ERROR: SKILL_LIBRARY_PATH not set and user.json 'library_path' missing. "
        "See references/user-config.md."
    )
BASE_DIR = _BASE_DIR_RESOLVED
SCORES_DIR = BASE_DIR / "scores"
SKILLS_BASE = BASE_DIR

# 8-Dimension Rubric (100pt total)
DIMENSIONS = {
    "frontmatter": {
        "max": 8,
        "weight": 0.08,
        "description": "name, description, triggers completeness",
    },
    "workflow": {
        "max": 15,
        "weight": 0.15,
        "description": "Step-by-step clarity, logical flow",
    },
    "edge_cases": {
        "max": 10,
        "weight": 0.10,
        "description": "Error handling, boundary conditions",
    },
    "checkpoints": {
        "max": 7,
        "weight": 0.07,
        "description": "Verification steps, quality gates",
    },
    "specificity": {
        "max": 15,
        "weight": 0.15,
        "description": "Action-level instructions vs vague",
    },
    "resources": {
        "max": 5,
        "weight": 0.05,
        "description": "Dependencies, external refs",
    },
    "architecture": {
        "max": 15,
        "weight": 0.15,
        "description": "Code structure, modularity",
    },
    "live_test": {
        "max": 25,
        "weight": 0.25,
        "description": "Real sub-agent execution + output quality",
    },
}

# 8 Clusters definition
CLUSTERS = {
    "document": [
        "docx",
        "pdf",
        "minimax-docx",
        "minimax-pdf",
        "lark-doc",
        "feishu-doc-reader",
    ],
    "frontend-ui": [
        "frontend-design",
        "design",
        "ui-ux-pro-max",
        "web-artifacts-builder",
        "canvas-design",
    ],
    "writing": ["write", "ljg-writes", "internal-comms", "doc-coauthoring"],
    "image": ["baoyu-image-gen", "gemini-image", "algorithmic-art", "brand-guidelines"],
    "spreadsheet": ["minimax-xlsx", "xlsx", "data-analysis"],
    "knowledge": [
        "learn",
        "ljg-learn",
        "ljg-paper",
        "ljg-paper-flow",
        "obsidian-markdown",
        "obsidian-bases",
    ],
    "seo-growth": ["money-seo", "baoyu-infographic"],
    "video": ["remotion-video", "ffmpeg-usage", "baoyu-slide-deck"],
}


def find_skill_path(skill_name: str) -> Optional[Path]:
    """Find skill directory by scanning BASE_DIR for SKILL.md files."""
    # Direct skill at root
    direct_path = SKILLS_BASE / skill_name / "SKILL.md"
    if direct_path.exists():
        return direct_path.parent

    # Check if skill_name contains a path
    if "/" in skill_name or "\\" in skill_name:
        alt_path = SKILLS_BASE / skill_name / "SKILL.md"
        if alt_path.exists():
            return alt_path.parent

    # Scan all subdirs for SKILL.md
    for item in SKILLS_BASE.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                # Check metadata name
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    if "---" in content:
                        parts = content.split("---")
                        if len(parts) >= 2:
                            import yaml

                            fm = yaml.safe_load(parts[1])
                            if fm and fm.get("name") == skill_name:
                                return item
                except:
                    pass

            # Check if dir name matches
            if item.name == skill_name:
                return item

            # Nested: skills/*/SKILL.md
            nested = item / "skills" / skill_name / "SKILL.md"
            if nested.exists():
                return nested.parent

    # Handle known subdir patterns: lark/*/SKILL.md
    for subdir in ["lark"]:
        subdir_path = SKILLS_BASE / subdir
        if subdir_path.exists():
            for item in subdir_path.iterdir():
                if item.is_dir():
                    skill_md = item / "SKILL.md"
                    if skill_md.exists():
                        try:
                            content = skill_md.read_text(encoding="utf-8")
                            if "---" in content:
                                parts = content.split("---")
                                if len(parts) >= 2:
                                    import yaml

                                    fm = yaml.safe_load(parts[1])
                                    if fm and fm.get("name") == skill_name:
                                        return item
                        except:
                            pass
                    if item.name == skill_name:
                        return item

    return None


def score_frontmatter(skill_path: Path) -> Dict[str, Any]:
    """Score Dim 1: Frontmatter completeness (0-8)"""
    score = 0
    notes = []
    max_score = 8

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return {"score": 0, "max": max_score, "notes": "SKILL.md not found"}

    try:
        content = skill_md.read_text(encoding="utf-8")
        if "---" not in content:
            notes.append("No frontmatter delimiter")
            return {"score": 0, "max": max_score, "notes": "; ".join(notes)}

        parts = content.split("---")
        if len(parts) < 2:
            notes.append("Invalid frontmatter format")
            return {"score": 0, "max": max_score, "notes": "; ".join(notes)}

        import yaml

        fm = yaml.safe_load(parts[1]) or {}

        # Check required fields
        if fm.get("name"):
            score += 2
        else:
            notes.append("Missing name")

        if fm.get("description"):
            score += 2
            if len(str(fm.get("description", ""))) > 50:
                score += 1  # Bonus for detailed description
        else:
            notes.append("Missing description")

        if fm.get("triggers") or fm.get("trigger"):
            score += 2
        else:
            notes.append("Missing triggers")

        if fm.get("scope") or fm.get("version"):
            score += 1

    except Exception as e:
        notes.append(f"Parse error: {str(e)}")

    return {
        "score": min(score, max_score),
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_workflow(content: str) -> Dict[str, Any]:
    """Score Dim 2: Workflow clarity (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    # Count workflow indicators
    has_steps = bool(re.search(r"(?i)(step\s*\d|步骤|task\s*\d|\d\.\s*\w)", content))
    has_clear_flow = bool(
        re.search(r"(?i)(first|then|next|finally|首先|然后|最后|流程)", content)
    )
    has_headers = len(re.findall(r"^#{1,3}\s+\w", content, re.MULTILINE))

    if has_steps:
        score += 5
    else:
        notes.append("No clear step indicators")

    if has_clear_flow:
        score += 5

    if has_headers >= 3:
        score += 5
    elif has_headers >= 1:
        score += 3

    # Length check (good workflows are detailed)
    if len(content) > 2000:
        score += 2
    elif len(content) > 500:
        score += 1

    return {
        "score": min(score, max_score),
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_edge_cases(content: str) -> Dict[str, Any]:
    """Score Dim 3: Edge cases handling (0-10)"""
    score = 0
    notes = []
    max_score = 10

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    # Check for error handling keywords
    error_patterns = [
        r"(?i)(error|exception|try\s*\{|catch|finally|错误|异常)",
        r"(?i)(if\s*not|unless|check\s*for|null|none|undefined|empty)",
        r"(?i)(timeout|retry|fallback|default|边界|极端)",
    ]

    error_count = 0
    for pattern in error_patterns:
        if re.search(pattern, content):
            error_count += 1

    score = min(error_count * 3, 10)

    if error_count == 0:
        notes.append("No explicit error handling found")

    return {
        "score": score,
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_checkpoints(content: str) -> Dict[str, Any]:
    """Score Dim 4: Checkpoints/verification steps (0-7)"""
    score = 0
    notes = []
    max_score = 7

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    # Check for verification indicators
    verify_patterns = [
        r"(?i)(verify|confirm|check|validation|验证|确认|检查)",
        r"(?i)(test|assert|expect|测试|断言)",
        r"(?i)(done|complete|finish|success|完成|成功)",
    ]

    verify_count = 0
    for pattern in verify_patterns:
        matches = re.findall(pattern, content)
        verify_count += len(matches)

    score = min(verify_count * 2, 7)

    if verify_count == 0:
        notes.append("No verification steps found")

    return {
        "score": score,
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_specificity(content: str) -> Dict[str, Any]:
    """Score Dim 5: Specificity - action-level vs vague (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    # Positive indicators (specific)
    specific_patterns = [
        r"(?i)(exact|specif|precise|具体)",
        r"\d+%|\d+\s*(times|seconds|minutes|hours|次|秒|分|时)",
        r"(?i)(always|never|whenever|无论何时)",
        r"```\w+",  # Code blocks indicate specificity
    ]

    # Negative indicators (vague)
    vague_patterns = [
        r"(?i)(maybe|perhaps|possibly|might|可能|也许)",
        r"(?i)(somehow|somewhat|有点|有些)",
        r"(?i)(etc|and so on|等等)",
    ]

    specific_count = sum(1 for p in specific_patterns if re.search(p, content))
    vague_count = sum(1 for p in vague_patterns if re.search(p, content))

    score = (specific_count * 3) - (vague_count * 2)
    score = max(0, min(score, max_score))

    if specific_count < 2:
        notes.append("Lacks specific details")

    return {
        "score": min(score, max_score),
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_resources(content: str) -> Dict[str, Any]:
    """Score Dim 6: Resources and dependencies (0-5)"""
    score = 0
    notes = []
    max_score = 5

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    # Check for resource indicators
    resource_patterns = [
        r"(?i)(requires?|needs?|dependencies|依赖)",
        r"(?i)(install|pip|npm|yarn|brew|安装)",
        r"(?i)(github|api|endpoint|url|link|链接)",
        r"(?i)(reference|docs?|文档)",
    ]

    resource_count = 0
    for pattern in resource_patterns:
        if re.search(pattern, content):
            resource_count += 1

    score = min(resource_count * 1.5, 5)

    if resource_count == 0:
        notes.append("No dependencies or resources documented")

    return {
        "score": min(int(score), max_score),
        "max": max_score,
        "notes": "; ".join(notes) if notes else "OK",
    }


def score_architecture(skill_path: Path) -> Dict[str, Any]:
    """Score Dim 7: Code structure and modularity (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not skill_path.exists():
        return {"score": 0, "max": max_score, "notes": "Skill path not found"}

    # Check for good structure indicators
    py_files = list(skill_path.rglob("*.py"))
    md_files = list(skill_path.rglob("*.md"))
    json_files = list(skill_path.rglob("*.json"))
    config_files = list(skill_path.rglob("*.yaml")) + list(skill_path.rglob("*.yml"))

    all_files = py_files + md_files + json_files + config_files

    # Score based on file count and organization
    if len(py_files) > 0:
        score += 3  # Has Python code
    if len(md_files) > 1:
        score += 2  # Multiple docs
    if len(json_files) > 0 or len(config_files) > 0:
        score += 2  # Has config

    # Check for modular structure
    if (skill_path / "__init__.py").exists():
        score += 3  # Proper Python package
    if (skill_path / "tests").exists() or (skill_path / "test_*.py").exists():
        score += 3  # Has tests

    # Check for subdirectories
    subdirs = [
        d for d in skill_path.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]
    if len(subdirs) >= 3:
        score += 2

    return {
        "score": min(score, max_score),
        "max": max_score,
        "notes": f"Files: {len(all_files)}, Py: {len(py_files)}",
    }


def score_live_test(skill_name: str, skill_path: Path) -> Dict[str, Any]:
    """Score Dim 8: Real sub-agent execution (0-25)"""
    max_score = 25

    # This will be executed via spawn_subagent in the actual scoring
    # Here we return a placeholder that will be filled by the sub-agent
    return {
        "score": 0,
        "max": max_score,
        "notes": "Live test pending - run via spawn_subagent",
        "agent_id": None,
        "task_output": None,
    }


def score_skill(skill_name: str, live_test: bool = True) -> Dict[str, Any]:
    """Score a single skill across all 8 dimensions."""
    result = {
        "skill_name": skill_name,
        "scored_at": datetime.now().isoformat(),
        "dimensions": {},
        "total": 0,
        "max_total": 100,
    }

    # Find skill path
    skill_path = find_skill_path(skill_name)
    if not skill_path:
        result["error"] = f"Skill not found: {skill_name}"
        return result

    result["skill_path"] = str(skill_path)

    # Read skill content
    skill_md = skill_path / "SKILL.md"
    content = ""
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")

    # Score each dimension
    result["dimensions"]["frontmatter"] = score_frontmatter(skill_path)
    result["dimensions"]["workflow"] = score_workflow(content)
    result["dimensions"]["edge_cases"] = score_edge_cases(content)
    result["dimensions"]["checkpoints"] = score_checkpoints(content)
    result["dimensions"]["specificity"] = score_specificity(content)
    result["dimensions"]["resources"] = score_resources(content)
    result["dimensions"]["architecture"] = score_architecture(skill_path)

    # Dim 8: Live test (placeholder - to be executed via sub-agent)
    if live_test:
        result["dimensions"]["live_test"] = score_live_test(skill_name, skill_path)
    else:
        result["dimensions"]["live_test"] = {
            "score": "pending",
            "max": 25,
            "notes": "Live test skipped - use spawn_subagent for real execution",
        }

    # Calculate total
    total = 0
    for dim_name, dim_data in result["dimensions"].items():
        if isinstance(dim_data.get("score"), (int, float)):
            total += dim_data["score"]
    result["total"] = total

    return result


def score_cluster(cluster_name: str, live_test: bool = True) -> List[Dict[str, Any]]:
    """Score all skills in a cluster."""
    if cluster_name not in CLUSTERS:
        print(f"Unknown cluster: {cluster_name}")
        print(f"Available clusters: {', '.join(CLUSTERS.keys())}")
        return []

    skills = CLUSTERS[cluster_name]
    results = []

    print(f"\n=== Scoring cluster: {cluster_name} ===")
    print(f"Skills: {', '.join(skills)}")

    for skill_name in skills:
        print(f"\nScoring: {skill_name}")
        result = score_skill(skill_name, live_test=live_test)
        if "error" not in result:
            print(f"  Total: {result['total']}/100")
            results.append(result)
        else:
            print(f"  ERROR: {result['error']}")

    # Sort by total score
    results.sort(key=lambda x: x["total"], reverse=True)

    # Add rank
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def save_score(score_data: Dict[str, Any], cluster_name: str):
    """Save score JSON to scores directory."""
    cluster_dir = SCORES_DIR / cluster_name
    cluster_dir.mkdir(parents=True, exist_ok=True)

    skill_name = score_data["skill_name"]
    output_file = cluster_dir / f"{skill_name}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(score_data, f, indent=2, ensure_ascii=False)

    print(f"  Saved: {output_file}")


def generate_report(cluster_name: str, scores: List[Dict[str, Any]]) -> str:
    """Generate Markdown comparison report for a cluster."""
    if not scores:
        return "# No scores available\n"

    report = f"""# {cluster_name.title()} Cluster Comparison Report

**Scored:** {datetime.now().strftime("%Y-%m-%d")} | **Skills:** {len(scores)}

## Comparison Table

| Rank | Skill | Total | Frontmatter | Workflow | Edge Cases | Checkpoints | Specificity | Resources | Architecture | Live Test |
|:----:|-------|------:|------------:|----------:|------------:|------------:|------------:|----------:|-------------:|----------:|
"""

    for s in scores:
        dims = s.get("dimensions", {})
        fm = dims.get("frontmatter", {}).get("score", 0)
        wf = dims.get("workflow", {}).get("score", 0)
        ec = dims.get("edge_cases", {}).get("score", 0)
        cp = dims.get("checkpoints", {}).get("score", 0)
        sp = dims.get("specificity", {}).get("score", 0)
        rs = dims.get("resources", {}).get("score", 0)
        ar = dims.get("architecture", {}).get("score", 0)
        lt = dims.get("live_test", {}).get("score", 0)

        lt_display = f"{lt}/25" if isinstance(lt, (int, float)) else lt

        report += f"| {s.get('rank', '-')} | {s.get('skill_name', '?')} | {s.get('total', 0)}/100 | {fm}/8 | {wf}/15 | {ec}/10 | {cp}/7 | {sp}/15 | {rs}/5 | {ar}/15 | {lt_display} |\n"

    # Top performers
    report += "\n## Top Performers by Dimension\n"
    for dim_name in [
        "frontmatter",
        "workflow",
        "edge_cases",
        "checkpoints",
        "specificity",
        "resources",
        "architecture",
        "live_test",
    ]:
        dim_max = DIMENSIONS[dim_name]["max"]
        best_score = 0
        best_skill = ""
        for s in scores:
            score = s.get("dimensions", {}).get(dim_name, {}).get("score", 0)
            if isinstance(score, (int, float)) and score > best_score:
                best_score = score
                best_skill = s.get("skill_name", "?")
        if best_skill:
            report += (
                f"- **{dim_name.title()}:** {best_skill} ({best_score}/{dim_max})\n"
            )

    # Decision section
    report += """
## Decision

**No auto-winner selected.** Review scores above and pick your winner manually.

Score ranges provide guidance on relative quality - the final choice should consider your specific use case and requirements.
"""

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Skill Scoring - 8-Dimension Evaluation (100pt)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python score.py --skill docx              Score single skill
  python score.py --cluster document        Score all skills in cluster
  python score.py --all                     Score all skills in all clusters
  python score.py --report --cluster document  Generate markdown report
        """,
    )

    parser.add_argument("--skill", type=str, help="Score a single skill by name")
    parser.add_argument("--cluster", type=str, help="Score all skills in a cluster")
    parser.add_argument(
        "--all", action="store_true", help="Score all skills in all clusters"
    )
    parser.add_argument(
        "--report", action="store_true", help="Generate markdown report"
    )
    parser.add_argument(
        "--no-live-test", action="store_true", help="Skip live test (Dim 8)"
    )
    parser.add_argument("--output", type=str, help="Output directory for scores")

    args = parser.parse_args()

    # Override scores dir if specified
    global SCORES_DIR
    if args.output:
        SCORES_DIR = Path(args.output)

    SCORES_DIR.mkdir(parents=True, exist_ok=True)

    live_test = not args.no_live_test

    if args.skill:
        # Score single skill
        result = score_skill(args.skill, live_test=live_test)
        print(f"\n=== Score: {args.skill} ===")
        print(f"Total: {result.get('total', 0)}/100")

        # Determine cluster
        cluster = "unknown"
        for cname, skills in CLUSTERS.items():
            if args.skill in skills:
                cluster = cname
                break

        save_score(result, cluster)
        print(f"\nScores saved to: scores/{cluster}/{args.skill}.json")

    elif args.cluster:
        # Score cluster
        if args.cluster not in CLUSTERS:
            print(f"Unknown cluster: {args.cluster}")
            print(f"Available: {', '.join(CLUSTERS.keys())}")
            return 1

        scores = score_cluster(args.cluster, live_test=live_test)

        # Save individual scores
        for score_data in scores:
            save_score(score_data, args.cluster)

        # Generate report
        if args.report:
            report = generate_report(args.cluster, scores)
            report_file = SCORES_DIR / args.cluster / "report.md"
            report_file.write_text(report, encoding="utf-8")
            print(f"\nReport saved to: {report_file}")

    elif args.all:
        # Score all clusters
        for cluster_name in CLUSTERS.keys():
            scores = score_cluster(cluster_name, live_test=live_test)
            for score_data in scores:
                save_score(score_data, cluster_name)

            if args.report and scores:
                report = generate_report(cluster_name, scores)
                report_file = SCORES_DIR / cluster_name / "report.md"
                report_file.write_text(report, encoding="utf-8")
                print(f"Report: {report_file}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
