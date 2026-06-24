"""Mandatory gate evaluation for skillctl v5.

Runs validate (structural + security + red-flag) and score (8-dim quality)
against a candidate skill path and assembles a frozen GateReport.

Score gate limitation: score.py --skill <name> requires the skill to already be
in the library index (<library>/.claude/skills/<name>/SKILL.md). For pre-land
gate evaluation, the skill is in a temp directory, not the library. In this case
score returns score_error="not in library index" — this does NOT cause gate
failure (score is informational only per v5 protocol).
"""
from __future__ import annotations

import json
import subprocess
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# sibling module — governance_validate.py has no env/prerequisite checks at import time
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from governance_validate import validate_skill


@dataclass(frozen=True)
class GateReport:
    """Immutable result of running both gates against a skill."""
    target_path: str
    validate_passed: bool
    validate_findings: list[dict] = field(default_factory=list)
    validate_error: Optional[str] = None
    score_value: Optional[int] = None
    score_dimensions: dict = field(default_factory=dict)
    score_error: Optional[str] = None
    timed_out: bool = False

    @property
    def gates_passed(self) -> bool:
        """Overall gate pass = validate passed AND no subprocess errors."""
        return self.validate_passed and self.validate_error is None and not self.timed_out


def run_gates(target: Path, *, timeout: int = 60) -> GateReport:
    """Run validate and score against `target`.

    Args:
        target: Path to skill directory (contains SKILL.md).
        timeout: Per-gate subprocess timeout in seconds.

    Returns:
        Frozen GateReport. Never raises — errors captured in fields.
    """
    target = Path(target).resolve()
    target_str = str(target)

    # ── Gate 1: validate_skill (direct import, no subprocess needed) ─────────
    validate_passed = False
    validate_findings: list[dict] = []
    validate_error: Optional[str] = None
    try:
        result = validate_skill(target)
        validate_passed = result.valid
        for issue in result.issues:
            validate_findings.append({
                "severity": issue.severity,
                "category": issue.category,
                "message": issue.message,
                "file_path": issue.file_path,
                "line": issue.line_number,
                "fix_suggestion": issue.fix_suggestion,
            })
    except Exception as e:
        validate_error = f"validate crashed: {e}"

    # ── Gate 2: score.py via subprocess ───────────────────────────────────────
    # score.py requires SKILL_LIBRARY_PATH and --skill <name> which performs
    # a library index lookup. For pre-land gates, the skill is in a temp dir,
    # not the library. We attempt score anyway but accept "not found" gracefully.
    score_value: Optional[int] = None
    score_dimensions: dict = {}
    score_error: Optional[str] = None

    skill_name = target.name
    scripts_dir = Path(__file__).resolve().parent.parent
    score_script = scripts_dir / "score.py"

    try:
        proc = subprocess.run(
            [sys.executable, str(score_script), "--skill", skill_name],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "SKILL_LIBRARY_PATH": str(target.parent)},
        )
        if proc.returncode == 0:
            # score.py prints human-readable output; try to parse JSON footer
            output = proc.stdout
            try:
                # Last JSON block in output if any
                for line in reversed(output.strip().splitlines()):
                    line = line.strip()
                    if line.startswith("{"):
                        data = json.loads(line)
                        score_value = data.get("total") or data.get("score")
                        score_dimensions = data.get("dimensions", {})
                        break
            except (json.JSONDecodeError, ValueError):
                # No parseable JSON — score printed human-readable report
                score_value = None
        elif "not found" in proc.stderr.lower() or "not found" in proc.stdout.lower():
            score_error = "not in library index"
        else:
            score_error = proc.stderr.strip() or f"score exited {proc.returncode}"
    except subprocess.TimeoutExpired:
        score_error = f"score timed out after {timeout}s"
    except Exception as e:
        score_error = f"score crashed: {e}"

    return GateReport(
        target_path=target_str,
        validate_passed=validate_passed,
        validate_findings=validate_findings,
        validate_error=validate_error,
        score_value=score_value,
        score_dimensions=score_dimensions,
        score_error=score_error,
    )


def format_report(report: GateReport) -> str:
    """Human-readable merged report for interactive prompt."""
    lines = []
    lines.append(f"=== Gate Report for {report.target_path} ===")
    lines.append("")
    lines.append("[Gate 1] validate --strict:")
    if report.validate_error:
        lines.append(f"  ERROR: {report.validate_error}")
    elif report.validate_passed:
        lines.append("  PASS")
    else:
        lines.append("  FAIL")
    for f in report.validate_findings[:10]:
        sev = f.get("severity", "?")
        msg = f.get("message", f.get("description", str(f)))
        line = f.get("line", "?")
        lines.append(f"    [{sev}] line {line}: {msg}")
    if len(report.validate_findings) > 10:
        lines.append(f"    ... and {len(report.validate_findings) - 10} more")
    lines.append("")
    lines.append("[Gate 2] score (informational, never aborts):")
    if report.score_error:
        lines.append(f"  {report.score_error}")
    elif report.score_value is not None:
        lines.append(f"  Total: {report.score_value}/100")
        for dim, val in report.score_dimensions.items():
            lines.append(f"    {dim}: {val}")
    else:
        lines.append("  (not scored)")
    lines.append("")
    overall = "PASS" if report.gates_passed else "FAIL"
    lines.append(f"Overall: {overall}")
    return "\n".join(lines)
