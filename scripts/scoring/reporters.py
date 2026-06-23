"""
Output Reporters

Generates JSON and Markdown output from scores.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def to_json(score_dict: Dict[str, Any]) -> str:
    """Convert score dict to JSON string."""
    return json.dumps(score_dict, indent=2, ensure_ascii=False)


def to_markdown_table(cluster_scores: List[Dict[str, Any]], cluster_name: str) -> str:
    """Generate Markdown comparison table for a cluster."""
    if not cluster_scores:
        return f"# {cluster_name.title()} Cluster - No Scores Available\n"

    from datetime import datetime
    from .rubrics import DIMENSIONS

    report = f"""# {cluster_name.title()} Cluster Comparison Report

**Scored:** {datetime.now().strftime('%Y-%m-%d')} | **Skills:** {len(cluster_scores)}

## Comparison Table

| Rank | Skill | Total | Frontmatter | Workflow | Edge Cases | Checkpoints | Specificity | Resources | Architecture | Live Test |
|:----:|-------|------:|------------:|----------:|------------:|------------:|------------:|----------:|-------------:|----------:|
"""

    for s in cluster_scores:
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

    report += "\n## Top Performers by Dimension\n"
    for dim_name in ["frontmatter", "workflow", "edge_cases", "checkpoints", "specificity", "resources", "architecture", "live_test"]:
        dim_max = DIMENSIONS[dim_name]["max"]
        best_score = 0
        best_skill = ""
        for s in cluster_scores:
            score = s.get("dimensions", {}).get(dim_name, {}).get("score", 0)
            if isinstance(score, (int, float)) and score > best_score:
                best_score = score
                best_skill = s.get("skill_name", "?")
        if best_skill:
            report += f"- **{dim_name.title()}:** {best_skill} ({best_score}/{dim_max})\n"

    report += """
## Decision

**No auto-winner selected.** Review scores above and pick your winner manually.

Score ranges provide guidance on relative quality - the final choice should consider your specific use case and requirements.
"""

    return report


def save_score(score_data: Dict[str, Any], output_dir: Path):
    """Save score JSON to output directory."""
    skill_name = score_data["skill_name"]

    # Determine cluster from path or default
    cluster_dir = output_dir
    if not cluster_dir.exists():
        cluster_dir.mkdir(parents=True, exist_ok=True)

    output_file = cluster_dir / f"{skill_name}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(score_data, f, indent=2, ensure_ascii=False)

    return output_file


def save_report(report_content: str, output_dir: Path):
    """Save markdown report to output directory."""
    report_file = output_dir / "report.md"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_file
