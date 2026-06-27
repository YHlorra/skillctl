#!/usr/bin/env python3
"""
Skill Manager - Governance Validation Module

对 skills 进行治理验证：
1. SKILL.md 结构验证（frontmatter 字段完整性）
2. 安全扫描（检测敏感信息：API keys, tokens, passwords）
3. 红标检查（常见问题模式）

Usage:
    python governance_validate.py                    # Validate all skills
    python governance_validate.py --skill <name>   # Validate single skill
    python governance_validate.py --fix            # Auto-fix some issues
    python governance_validate.py --json           # Output JSON format
"""

import os
import sys
import re
import json
import yaml
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from _lib.paths import expand_path
from _lib.paths import expand_path

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

@dataclass
class ValidationIssue:
    """A validation issue found in a skill."""
    skill_name: str
    skill_path: str
    severity: str  # "error", "warning", "info"
    category: str  # "structure", "security", "redflag"
    message: str
    file_path: str
    line_number: Optional[int] = None
    fix_suggestion: Optional[str] = None

@dataclass
class ValidationResult:
    """Result of validating a skill."""
    skill_name: str
    skill_path: str
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    score: int = 100  # Governance score (100 = perfect)
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, EXTREME

# Required frontmatter fields
REQUIRED_FIELDS = {
    "name": {"type": str, "required": True},
    "description": {"type": str, "required": True},
}

# Recommended frontmatter fields
RECOMMENDED_FIELDS = {
    "version": {"type": str, "required": False},
    "scope": {"type": str, "required": False},  # global | project
    "source_type": {"type": str, "required": False},  # github | local | derived
    "github_url": {"type": str, "required": False},
    "github_hash": {"type": str, "required": False},
}

# Security patterns to detect
SECURITY_PATTERNS = [
    # API Keys and Tokens
    (r"api[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]", "API Key detected", "high"),
    (r"secret[_-]?key\s*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]", "Secret Key detected", "high"),
    (r"password\s*[=:]\s*['\"][^'\"]{8,}['\"]", "Password detected", "high"),
    (r"token\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]", "Token detected", "high"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token detected", "high"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key detected", "high"),
    (r"AIza[a-zA-Z0-9_-]{35}", "Google API Key detected", "high"),
    (r"sk_live_[a-zA-Z0-9]{24,}", "Stripe Live Key detected", "high"),
    (r"AKIA[a-zA-Z0-9]{16}", "AWS Access Key detected", "high"),

    # Network Security Issues
    (r"curl\s+['\"]https?://[^'\"]+['\"]\s+(-o|--output)", "curl download to unknown URL", "high"),
    (r"wget\s+['\"]https?://[^'\"]+['\"]", "wget from unknown URL", "high"),
    (r"requests\.get\s*\(['\"]http://", "HTTP (not HTTPS) request - insecure", "medium"),
    (r"urllib\.request\.urlopen\s*\(['\"]http://", "urllib HTTP request - insecure", "medium"),

    # Suspicious Behaviors
    (r"base64\.(decode|b64decode)\s*\(", "base64 decode detected - possible obfuscation", "high"),
    (r"__import__\s*\(['\"]", "__import__ dynamic import detected", "high"),
    (r"import\s+lib\s*\.", "Dynamic library import", "medium"),

    # Credential Access
    (r"\~/.ssh/", "Access to SSH directory", "high"),
    (r"\~/.aws/", "Access to AWS credentials directory", "high"),
    (r"\~/.config/", "Access to config directory", "medium"),
    (r"MEMORY\.md|USER\.md|SOUL\.md|IDENTITY\.md", "Access to agent memory/identity files", "high"),
]

# Red flag patterns
RED_FLAG_PATTERNS = [
    # Debug and Development Issues
    (r"TODO(?!\w)", "TODO comment without action", "warning"),
    (r"FIXME(?!\w)", "FIXME comment without fix", "warning"),
    (r"HACK(?!\w)", "HACK comment found", "warning"),
    (r"XXX(?!\w)", "XXX comment found", "warning"),
    (r"\bconsole\.(log|debug|info)\s*\(", "Debug console statement", "info"),
    (r"print\s*\(.*\)", "Print statement (should be logging)", "info"),

    # Security Risks
    (r"import\s+.*\s+from\s+['\"]powershell", "PowerShell import detected", "warning"),
    (r"os\.system\s*\(", "os.system() call - potential shell injection", "warning"),
    (r"subprocess\.call\s*\([^)]*shell\s*=\s*True", "shell=True in subprocess - security risk", "error"),
    (r"eval\s*\(", "eval() usage - potential code injection", "error"),
    (r"exec\s*\(", "exec() usage - potential code injection", "error"),

    # Network Issues
    (r"net\s*\.connect\s*\(", "Raw network socket connection", "medium"),
    (r"socket\s*\.socket\s*\(", "Raw socket creation", "medium"),

    # System Modification
    (r"os\.chmod\s*\(", "Changing file permissions", "warning"),
    (r"os\.chown\s*\(", "Changing file ownership", "warning"),
    (r"mkdir\s*\([^)]*mode\s*=", "Creating directory with permissions", "info"),
]

# Risk classification based on patterns found
RISK_PATTERNS = {
    "credential_access": ["~/.ssh/", "~/.aws/", "MEMORY.md", "USER.md", "SOUL.md", "IDENTITY.md"],
    "external_network": ["curl ", "wget ", "requests.get(", "urllib.request.urlopen"],
    "code_execution": ["eval(", "exec(", "__import__", "os.system"],
    "shell_injection": ["shell=True", "os.system"],
}

# Description quality checks
DESCRIPTION_MIN_LENGTH = 20
DESCRIPTION_MAX_LENGTH = 300

def parse_frontmatter(content: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse YAML frontmatter from SKILL.md content."""
    parts = content.split("---")
    if len(parts) < 3:
        return None, "No frontmatter found (expected --- delimiters)"

    try:
        frontmatter = yaml.safe_load(parts[1])
        return frontmatter, None
    except yaml.YAMLError as e:
        return None, f"YAML parse error: {e}"

def validate_frontmatter(
    frontmatter: Dict, skill_path: Path
) -> List[ValidationIssue]:
    """Validate frontmatter fields."""
    issues = []

    if not frontmatter:
        issues.append(
            ValidationIssue(
                skill_name=skill_path.parent.name,
                skill_path=str(skill_path.parent),
                severity="error",
                category="structure",
                message="Empty or missing frontmatter",
                file_path=str(skill_path),
            )
        )
        return issues

    skill_name = frontmatter.get("name", skill_path.parent.name)

    # Check required fields
    for field_name, field_spec in REQUIRED_FIELDS.items():
        if field_spec["required"] and field_name not in frontmatter:
            issues.append(
                ValidationIssue(
                    skill_name=skill_name,
                    skill_path=str(skill_path.parent),
                    severity="error",
                    category="structure",
                    message=f"Required field '{field_name}' is missing",
                    file_path=str(skill_path),
                    fix_suggestion=f"Add '{field_name}' to frontmatter",
                )
            )

    # Check description quality
    description = frontmatter.get("description", "")
    if isinstance(description, list):
        description = " ".join(description)

    if description:
        desc_len = len(description)
        if desc_len < DESCRIPTION_MIN_LENGTH:
            issues.append(
                ValidationIssue(
                    skill_name=skill_name,
                    skill_path=str(skill_path.parent),
                    severity="warning",
                    category="structure",
                    message=f"Description too short ({desc_len} chars, min {DESCRIPTION_MIN_LENGTH})",
                    file_path=str(skill_path),
                    fix_suggestion="Expand description with more details about triggers and use cases",
                )
            )
        elif desc_len > DESCRIPTION_MAX_LENGTH:
            issues.append(
                ValidationIssue(
                    skill_name=skill_name,
                    skill_path=str(skill_path.parent),
                    severity="info",
                    category="structure",
                    message=f"Description too long ({desc_len} chars, max {DESCRIPTION_MAX_LENGTH})",
                    file_path=str(skill_path),
                    fix_suggestion="Truncate description or split into multiple lines",
                )
            )

    # Check field types
    for field_name, field_spec in {**REQUIRED_FIELDS, **RECOMMENDED_FIELDS}.items():
        if field_name in frontmatter:
            value = frontmatter[field_name]
            expected_type = field_spec["type"]
            if not isinstance(value, expected_type):
                issues.append(
                    ValidationIssue(
                        skill_name=skill_name,
                        skill_path=str(skill_path.parent),
                        severity="warning",
                        category="structure",
                        message=f"Field '{field_name}' has wrong type (expected {expected_type.__name__}, got {type(value).__name__})",
                        file_path=str(skill_path),
                        fix_suggestion=f"Change '{field_name}' value to {expected_type.__name__}",
                    )
                )

    # Check scope value
    scope = frontmatter.get("scope")
    if scope and scope not in ("global", "project"):
        issues.append(
            ValidationIssue(
                skill_name=skill_name,
                skill_path=str(skill_path.parent),
                severity="warning",
                category="structure",
                message=f"Invalid scope value '{scope}' (expected 'global' or 'project')",
                file_path=str(skill_path),
                fix_suggestion="Set scope to 'global' or 'project'",
            )
        )

    return issues

def check_security_issues(
    skill_path: Path, skill_name: str
) -> List[ValidationIssue]:
    """Scan skill files for security issues."""
    issues = []

    # Skip common non-skill directories
    skip_dirs = {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist", ".tox", ".eggs", "*.egg-info"}

    # Check all files in skill directory
    for file_path in skill_path.rglob("*"):
        if file_path.is_dir():
            continue

        # Skip non-skill directories
        if any(s in file_path.parts for s in skip_dirs):
            continue

        # Skip certain file types
        if file_path.suffix in (".pyc", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2"):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            for pattern, message, severity in SECURITY_PATTERNS:
                matches = list(re.finditer(pattern, content, re.IGNORECASE))
                for match in matches:
                    line_number = content[: match.start()].count("\n") + 1
                    issues.append(
                        ValidationIssue(
                            skill_name=skill_name,
                            skill_path=str(skill_path),
                            severity=severity,
                            category="security",
                            message=message,
                            file_path=str(file_path.relative_to(skill_path)),
                            line_number=line_number,
                            fix_suggestion="Remove or replace with environment variable reference",
                        )
                    )

        except Exception:
            pass

    return issues

def check_red_flags(
    skill_path: Path, skill_name: str
) -> List[ValidationIssue]:
    """Check for red flag patterns."""
    issues = []

    # Skip common non-skill directories
    skip_dirs = {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", "build", "dist", ".tox", ".eggs", "*.egg-info"}

    # Check all text files
    for file_path in skill_path.rglob("*"):
        if file_path.is_dir():
            continue

        if any(s in file_path.parts for s in skip_dirs):
            continue

        if file_path.suffix in (".pyc", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2", ".bin"):
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                for pattern, message, severity in RED_FLAG_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        issues.append(
                            ValidationIssue(
                                skill_name=skill_name,
                                skill_path=str(skill_path),
                                severity=severity,
                                category="redflag",
                                message=message,
                                file_path=str(file_path.relative_to(skill_path)),
                                line_number=line_num,
                                fix_suggestion=f"Review and address: {message}",
                            )
                        )

        except Exception:
            pass

    return issues

def classify_risk_level(issues: List[ValidationIssue]) -> str:
    """
    Classify risk level based on detected issues.

    Risk Levels:
    - LOW: Basic review, safe to use
    - MEDIUM: Full code review required
    - HIGH: Human approval required
    - EXTREME: Do NOT install
    """
    categories = {i.category for i in issues}
    messages = {i.message for i in issues}

    # EXTREME - credential access or severe security issues
    if any("credential" in c or "token" in m.lower() or "password" in m.lower()
           for c in categories for m in messages if hasattr(m, 'lower')):
        return "EXTREME"
    if any("GitHub Personal Access Token" in m or "OpenAI API Key" in m
           or "AWS Access Key" in m or "Stripe" in m for m in messages):
        return "EXTREME"

    # HIGH - code injection, shell injection risks
    if any("eval(" in m or "exec(" in m or "shell=True" in m or "MEMORY.md" in m
           or "USER.md" in m or "curl " in m or "wget " in m for m in messages):
        return "HIGH"

    # MEDIUM - network access, suspicious patterns
    if any("credential_access" in c or "external_network" in c
           or "http://" in m or "base64" in m.lower()
           or "powershell" in m.lower() for c in categories for m in messages if hasattr(m, 'lower')):
        return "MEDIUM"

    # LOW - only minor issues
    if any(i.severity == "error" for i in issues):
        return "MEDIUM"
    if any(i.severity == "warning" for i in issues):
        return "LOW"

    return "LOW"

RISK_LEVEL_EMOJI = {
    "LOW": "🟢",
    "MEDIUM": "🟡",
    "HIGH": "🔴",
    "EXTREME": "⛔",
}

def validate_skill(skill_path: Path) -> ValidationResult:
    """Validate a single skill."""
    skill_name = skill_path.name
    skill_md = skill_path / "SKILL.md"

    if not skill_md.exists():
        return ValidationResult(
            skill_name=skill_name,
            skill_path=str(skill_path),
            valid=False,
            issues=[
                ValidationIssue(
                    skill_name=skill_name,
                    skill_path=str(skill_path),
                    severity="error",
                    category="structure",
                    message="SKILL.md not found",
                    file_path=str(skill_path),
                )
            ],
            score=0,
        )

    issues = []

    # Parse and validate frontmatter
    try:
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, error = parse_frontmatter(content)

        if error:
            issues.append(
                ValidationIssue(
                    skill_name=skill_name,
                    skill_path=str(skill_path),
                    severity="error",
                    category="structure",
                    message=error,
                    file_path=str(skill_md),
                )
            )
        else:
            issues.extend(validate_frontmatter(frontmatter, skill_path))
    except Exception as e:
        issues.append(
            ValidationIssue(
                skill_name=skill_name,
                skill_path=str(skill_path),
                severity="error",
                category="structure",
                message=f"Failed to read SKILL.md: {e}",
                file_path=str(skill_md),
            )
        )

    # Security scan
    issues.extend(check_security_issues(skill_path, skill_name))

    # Red flag check
    issues.extend(check_red_flags(skill_path, skill_name))

    # Calculate governance score
    score = 100
    for issue in issues:
        if issue.severity == "error":
            score -= 20
        elif issue.severity == "warning":
            score -= 5
        elif issue.severity == "info":
            score -= 1
    score = max(0, score)

    valid = not any(i.severity == "error" for i in issues)

    # Calculate risk level
    risk_level = classify_risk_level(issues)

    return ValidationResult(
        skill_name=skill_name,
        skill_path=str(skill_path),
        valid=valid,
        issues=issues,
        score=score,
        risk_level=risk_level,
    )

def load_index(index_path: Path) -> Dict:
    """Load index.json."""
    if not index_path.exists():
        return {}
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_all(skills_dir: Path, skill_name: Optional[str] = None) -> List[ValidationResult]:
    """Validate all skills in a directory."""
    results = []

    if not skills_dir.exists():
        return results

    for item in skills_dir.iterdir():
        if not item.is_dir():
            continue

        if skill_name and item.name != skill_name:
            continue

        # Skip certain directories
        if item.name.startswith(".") or item.name.startswith("_"):
            continue

        result = validate_skill(item)
        results.append(result)

    return results

def print_results_table(results: List[ValidationResult], verbose: bool = False):
    """Print validation results in a formatted table."""
    if not results:
        print("No skills to validate.")
        return

    # Sort by score (lowest first)
    results.sort(key=lambda x: x.score)

    print(f"\n{'=' * 110}")
    print(f" Governance Validation Results ({len(results)} skills)")
    print(f"{'=' * 110}")
    print(f"{'Skill':<30} {'Score':<8} {'Risk':<10} {'Valid':<8} {'Errors':<8} {'Warnings':<10} {'Info':<8} Issues")
    print("-" * 110)

    for r in results:
        errors = sum(1 for i in r.issues if i.severity == "error")
        warnings = sum(1 for i in r.issues if i.severity == "warning")
        info = sum(1 for i in r.issues if i.severity == "info")
        valid_str = "✓" if r.valid else "✗"
        risk_emoji = RISK_LEVEL_EMOJI.get(r.risk_level, "⚪")
        risk_str = f"{risk_emoji} {r.risk_level}"
        print(
            f"{r.skill_name:<30} {r.score:<8} {risk_str:<10} {valid_str:<8} {errors:<8} {warnings:<10} {info:<8} "
            f"{len(r.issues)}"
        )

    print("-" * 100)

    # Summary
    total_issues = sum(len(r.issues) for r in results)
    total_errors = sum(1 for r in results for i in r.issues if i.severity == "error")
    total_warnings = sum(1 for r in results for i in r.issues if i.severity == "warning")

    print(f"\nSummary:")
    print(f"  Total skills: {len(results)}")
    print(f"  Valid skills: {sum(1 for r in results if r.valid)}")
    print(f"  Total issues: {total_issues}")
    print(f"    Errors: {total_errors}")
    print(f"    Warnings: {total_warnings}")

    if verbose:
        print(f"\n{'=' * 100}")
        print(" Detailed Issues")
        print(f"{'=' * 100}")

        for r in results:
            if not r.issues:
                continue

            print(f"\n### {r.skill_name} ({r.score}/100)")
            print(f"   Path: {r.skill_path}")

            for i in sorted(r.issues, key=lambda x: (x.severity != "error", x.category)):
                severity_marker = "✗" if i.severity == "error" else "⚠" if i.severity == "warning" else "ℹ"
                loc = f":{i.line_number}" if i.line_number else ""
                print(f"   {severity_marker} [{i.category}] {i.message}")
                print(f"      File: {i.file_path}{loc}")
                if i.fix_suggestion:
                    print(f"      Fix: {i.fix_suggestion}")

def print_results_json(results: List[ValidationResult]):
    """Print results as JSON."""
    output = {
        "check_time": datetime.now().isoformat(),
        "total_skills": len(results),
        "valid_skills": sum(1 for r in results if r.valid),
        "total_issues": sum(len(r.issues) for r in results),
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - Governance Validation"
    )
    parser.add_argument(
        "--skills-dir", "-d", type=str, help="Skills directory to validate"
    )
    parser.add_argument(
        "--skill", "-s", type=str, help="Validate specific skill only"
    )
    parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed issues"
    )

    args = parser.parse_args()

    # Determine skills directory
    if args.skills_dir:
        skills_dir = expand_path(args.skills_dir)
    else:
        # Default to parent of skillctl
        script_dir = Path(__file__).parent
        skills_dir = script_dir.parent

    # Validate
    results = validate_all(skills_dir, args.skill)

    if not results:
        print("No skills found to validate.")
        return 0

    # Output
    if args.json:
        print_results_json(results)
    else:
        print_results_table(results, verbose=args.verbose)

    # Return exit code based on validity
    if any(not r.valid for r in results):
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())