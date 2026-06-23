"""
Core Scoring Engine

Implements the 8-dimension scoring logic.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml


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

        fm = yaml.safe_load(parts[1]) or {}

        if fm.get("name"):
            score += 2
        else:
            notes.append("Missing name")

        if fm.get("description"):
            score += 2
            if len(str(fm.get("description", ""))) > 50:
                score += 1
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

    return {"score": min(score, max_score), "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_workflow(content: str) -> Dict[str, Any]:
    """Score Dim 2: Workflow clarity (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    has_steps = bool(re.search(r'(?i)(step\s*\d|步骤|task\s*\d|\d\.\s*\w)', content))
    has_clear_flow = bool(re.search(r'(?i)(first|then|next|finally|首先|然后|最后|流程)', content))
    has_headers = len(re.findall(r'^#{1,3}\s+\w', content, re.MULTILINE))

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

    if len(content) > 2000:
        score += 2
    elif len(content) > 500:
        score += 1

    return {"score": min(score, max_score), "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_edge_cases(content: str) -> Dict[str, Any]:
    """Score Dim 3: Edge cases handling (0-10)"""
    score = 0
    notes = []
    max_score = 10

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    error_patterns = [
        r'(?i)(error|exception|try\s*\{|catch|finally|错误|异常)',
        r'(?i)(if\s*not|unless|check\s*for|null|none|undefined|empty)',
        r'(?i)(timeout|retry|fallback|default|边界|极端)',
    ]

    error_count = 0
    for pattern in error_patterns:
        if re.search(pattern, content):
            error_count += 1

    score = min(error_count * 3, 10)

    if error_count == 0:
        notes.append("No explicit error handling found")

    return {"score": score, "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_checkpoints(content: str) -> Dict[str, Any]:
    """Score Dim 4: Checkpoints/verification steps (0-7)"""
    score = 0
    notes = []
    max_score = 7

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    verify_patterns = [
        r'(?i)(verify|confirm|check|validation|验证|确认|检查)',
        r'(?i)(test|assert|expect|测试|断言)',
        r'(?i)(done|complete|finish|success|完成|成功)',
    ]

    verify_count = 0
    for pattern in verify_patterns:
        matches = re.findall(pattern, content)
        verify_count += len(matches)

    score = min(verify_count * 2, 7)

    if verify_count == 0:
        notes.append("No verification steps found")

    return {"score": score, "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_specificity(content: str) -> Dict[str, Any]:
    """Score Dim 5: Specificity - action-level vs vague (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    specific_patterns = [
        r'(?i)(exact|specif|precise|具体)',
        r'\d+%|\d+\s*(times|seconds|minutes|hours|次|秒|分|时)',
        r'(?i)(always|never|whenever|无论何时)',
        r'```\w+',
    ]

    vague_patterns = [
        r'(?i)(maybe|perhaps|possibly|might|可能|也许)',
        r'(?i)(somehow|somewhat|有点|有些)',
        r'(?i)(etc|and so on|等等)',
    ]

    specific_count = sum(1 for p in specific_patterns if re.search(p, content))
    vague_count = sum(1 for p in vague_patterns if re.search(p, content))

    score = (specific_count * 3) - (vague_count * 2)
    score = max(0, min(score, max_score))

    if specific_count < 2:
        notes.append("Lacks specific details")

    return {"score": min(score, max_score), "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_resources(content: str) -> Dict[str, Any]:
    """Score Dim 6: Resources and dependencies (0-5)"""
    score = 0
    notes = []
    max_score = 5

    if not content:
        return {"score": 0, "max": max_score, "notes": "No content"}

    resource_patterns = [
        r'(?i)(requires?|needs?|dependencies|依赖)',
        r'(?i)(install|pip|npm|yarn|brew|安装)',
        r'(?i)(github|api|endpoint|url|link|链接)',
        r'(?i)(reference|docs?|文档)',
    ]

    resource_count = 0
    for pattern in resource_patterns:
        if re.search(pattern, content):
            resource_count += 1

    score = min(resource_count * 1.5, 5)

    if resource_count == 0:
        notes.append("No dependencies or resources documented")

    return {"score": min(int(score), max_score), "max": max_score, "notes": "; ".join(notes) if notes else "OK"}


def score_architecture(skill_path: Path) -> Dict[str, Any]:
    """Score Dim 7: Code structure and modularity (0-15)"""
    score = 0
    notes = []
    max_score = 15

    if not skill_path.exists():
        return {"score": 0, "max": max_score, "notes": "Skill path not found"}

    py_files = list(skill_path.rglob("*.py"))
    md_files = list(skill_path.rglob("*.md"))
    json_files = list(skill_path.rglob("*.json"))
    config_files = list(skill_path.rglob("*.yaml")) + list(skill_path.rglob("*.yml"))

    all_files = py_files + md_files + json_files + config_files

    if len(py_files) > 0:
        score += 3
    if len(md_files) > 1:
        score += 2
    if len(json_files) > 0 or len(config_files) > 0:
        score += 2

    if (skill_path / "__init__.py").exists():
        score += 3
    if (skill_path / "tests").exists() or (skill_path / "test_*.py").exists():
        score += 3

    subdirs = [d for d in skill_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
    if len(subdirs) >= 3:
        score += 2

    return {"score": min(score, max_score), "max": max_score, "notes": f"Files: {len(all_files)}, Py: {len(py_files)}"}


def find_skill_path(skill_name: str, base_path: Path) -> Optional[Path]:
    """Find skill directory by scanning base_path for SKILL.md files."""
    # Direct skill at root
    direct_path = base_path / skill_name / "SKILL.md"
    if direct_path.exists():
        return direct_path.parent

    # Check if skill_name contains a path
    if "/" in skill_name or "\\" in skill_name:
        alt_path = base_path / skill_name / "SKILL.md"
        if alt_path.exists():
            return alt_path.parent

    # Scan all subdirs for SKILL.md
    for item in base_path.iterdir():
        if item.is_dir():
            skill_md = item / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    if "---" in content:
                        parts = content.split("---")
                        if len(parts) >= 2:
                            fm = yaml.safe_load(parts[1])
                            if fm and fm.get("name") == skill_name:
                                return item
                except:
                    pass

            if item.name == skill_name:
                return item

            nested = item / "skills" / skill_name / "SKILL.md"
            if nested.exists():
                return nested.parent

    return None


def score_skill(skill_name: str, base_path: Path, live_test: bool = True) -> Dict[str, Any]:
    """Score a single skill across all 8 dimensions."""
    from datetime import datetime
    from .live_test import execute_live_test

    result = {
        "skill_name": skill_name,
        "scored_at": datetime.now().isoformat(),
        "dimensions": {},
        "total": 0,
        "max_total": 100,
    }

    skill_path = find_skill_path(skill_name, base_path)
    if not skill_path:
        result["error"] = f"Skill not found: {skill_name}"
        return result

    result["skill_path"] = str(skill_path)

    skill_md = skill_path / "SKILL.md"
    content = ""
    if skill_md.exists():
        content = skill_md.read_text(encoding="utf-8")

    result["dimensions"]["frontmatter"] = score_frontmatter(skill_path)
    result["dimensions"]["workflow"] = score_workflow(content)
    result["dimensions"]["edge_cases"] = score_edge_cases(content)
    result["dimensions"]["checkpoints"] = score_checkpoints(content)
    result["dimensions"]["specificity"] = score_specificity(content)
    result["dimensions"]["resources"] = score_resources(content)
    result["dimensions"]["architecture"] = score_architecture(skill_path)

    if live_test:
        result["dimensions"]["live_test"] = execute_live_test(skill_name, skill_path)
    else:
        result["dimensions"]["live_test"] = {
            "score": "pending",
            "max": 25,
            "notes": "Live test skipped"
        }

    total = 0
    for dim_name, dim_data in result["dimensions"].items():
        if isinstance(dim_data.get("score"), (int, float)):
            total += dim_data["score"]
    result["total"] = total

    return result


def score_cluster(cluster_name: str, base_path: Path, live_test: bool = True) -> List[Dict[str, Any]]:
    """Score all skills in a cluster."""
    from .clusters import CLUSTERS

    if cluster_name not in CLUSTERS:
        return []

    skills = CLUSTERS[cluster_name]
    results = []

    for skill_name in skills:
        result = score_skill(skill_name, base_path, live_test=live_test)
        if "error" not in result:
            results.append(result)

    results.sort(key=lambda x: x["total"], reverse=True)

    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
