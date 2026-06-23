#!/usr/bin/env python3
"""
Skill Manager - Score History Module

追踪 skills 的评分历史，检测回归（分数下降）。
保存历史评分到 JSON 文件，支持趋势分析和回归检测。

Usage:
    python score_history.py --record              # Record current scores
    python score_history.py --trend <skill>       # Show score trend for skill
    python score_history.py --regressions         # Show skills with score drops
    python score_history.py --report              # Full history report
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

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
SCORE_HISTORY_FILE = BASE_DIR / ".skillctl" / "score_history.json"


@dataclass
class ScoreEntry:
    """A single score entry for a skill."""
    timestamp: str
    score: int
    dimensions: Dict[str, int] = field(default_factory=dict)
    note: str = ""


@dataclass
class SkillScoreHistory:
    """Score history for a single skill."""
    skill_name: str
    entries: List[ScoreEntry] = field(default_factory=list)

    @property
    def latest_score(self) -> Optional[int]:
        if self.entries:
            return self.entries[-1].score
        return None

    @property
    def previous_score(self) -> Optional[int]:
        if len(self.entries) >= 2:
            return self.entries[-2].score
        return None

    @property
    def delta(self) -> Optional[int]:
        if self.latest_score is not None and self.previous_score is not None:
            return self.latest_score - self.previous_score
        return None

    @property
    def trend(self) -> str:
        d = self.delta
        if d is None:
            return "no-history"
        elif d > 0:
            return "improving"
        elif d < 0:
            return "regression"
        return "stable"


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def load_score_history() -> Dict[str, SkillScoreHistory]:
    """Load score history from JSON file."""
    SCORE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not SCORE_HISTORY_FILE.exists():
        return {}

    try:
        with open(SCORE_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        result = {}
        for skill_name, skill_data in data.items():
            entries = [ScoreEntry(**e) for e in skill_data.get("entries", [])]
            result[skill_name] = SkillScoreHistory(skill_name=skill_name, entries=entries)
        return result
    except Exception as e:
        print(f"Warning: Failed to load score history: {e}")
        return {}


def save_score_history(history: Dict[str, SkillScoreHistory]):
    """Save score history to JSON file."""
    SCORE_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    for skill_name, skill_history in history.items():
        data[skill_name] = {
            "skill_name": skill_name,
            "entries": [
                {
                    "timestamp": e.timestamp,
                    "score": e.score,
                    "dimensions": e.dimensions,
                    "note": e.note,
                }
                for e in skill_history.entries
            ],
        }

    with open(SCORE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_latest_scores_from_reports() -> Dict[str, Dict]:
    """Get latest scores from score reports if they exist."""
    scores = {}

    # Look for scores in various locations
    search_paths = [
        BASE_DIR / "scores",
        BASE_DIR / "skillctl" / "scores",
    ]

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Look for score JSON files
        for cluster_dir in search_path.iterdir():
            if not cluster_dir.is_dir():
                continue

            score_file = cluster_dir / "score.json"
            if score_file.exists():
                try:
                    with open(score_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for skill_name, skill_data in data.items():
                            if skill_name not in scores:
                                scores[skill_name] = skill_data
                except Exception:
                    pass

    return scores


def parse_score_from_skill_md(skill_path: Path) -> Optional[Dict]:
    """Try to parse score from skill's own data."""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return None

    try:
        content = skill_md.read_text(encoding="utf-8")
        parts = content.split("---")
        if len(parts) >= 3:
            import yaml
            frontmatter = yaml.safe_load(parts[1])
            score = frontmatter.get("governance_score") or frontmatter.get("score")
            if score:
                return {"score": score}
    except Exception:
        pass

    return None


def record_scores():
    """Record current scores for all skills."""
    history = load_score_history()
    timestamp = datetime.now().isoformat()

    # Get current index
    index_path = BASE_DIR / "skillctl" / "index.json"
    if not index_path.exists():
        print(f"Error: index.json not found at {index_path}")
        print("Hint: Run 'python scan_and_index.py' first")
        return 1

    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    skills = index.get("skills", {})
    recorded = 0
    skipped = 0

    for skill_name, skill_data in skills.items():
        locations = skill_data.get("locations", [])
        real_loc = next((l for l in locations if not l.get("is_symlink")), locations[0] if locations else None)

        if not real_loc:
            skipped += 1
            continue

        skill_path = expand_path(real_loc["path"])

        # Try to get score from various sources
        score = None
        dimensions = {}

        # 1. Check score reports
        latest_scores = get_latest_scores_from_reports()
        if skill_name in latest_scores:
            score = latest_scores[skill_name].get("total_score")

        # 2. Check skill's own metadata
        if not score:
            skill_score_data = parse_score_from_skill_md(skill_path)
            if skill_score_data:
                score = skill_score_data.get("score")

        if score is None:
            skipped += 1
            continue

        # Add entry to history
        if skill_name not in history:
            history[skill_name] = SkillScoreHistory(skill_name=skill_name)

        entry = ScoreEntry(
            timestamp=timestamp,
            score=int(score),
            dimensions=dimensions,
        )
        history[skill_name].entries.append(entry)
        recorded += 1

    save_score_history(history)

    print(f"\n✓ Recorded {recorded} scores at {timestamp}")
    if skipped > 0:
        print(f"  (skipped {skipped} skills without scores)")

    return 0


def show_trend(skill_name: str):
    """Show score trend for a specific skill."""
    history = load_score_history()

    if skill_name not in history:
        print(f"No score history for '{skill_name}'")
        return 1

    skill_history = history[skill_name]

    if not skill_history.entries:
        print(f"No score history for '{skill_name}'")
        return 1

    print(f"\n{'=' * 60}")
    print(f" Score Trend: {skill_name}")
    print(f"{'=' * 60}")

    print(f"{'Date':<28} {'Score':<10} {'Delta':<10} {'Trend'}")
    print("-" * 60)

    for i, entry in enumerate(skill_history.entries):
        delta = ""
        trend = ""

        if i > 0:
            prev = skill_history.entries[i - 1].score
            d = entry.score - prev
            delta = f"{d:+d}"
            if d > 0:
                trend = "↑ improving"
            elif d < 0:
                trend = "↓ regression"
            else:
                trend = "→ stable"

        print(f"{entry.timestamp:<28} {entry.score:<10} {delta:<10} {trend}")

    print("-" * 60)
    print(f"Latest: {skill_history.latest_score} ({skill_history.trend})")

    if skill_history.trend == "regression":
        print("\n⚠ WARNING: Score has regressed!")
        print("   Run 'python git_rollback.py --skill <name>' to review changes")

    return 0


def show_regressions():
    """Show all skills with score regressions."""
    history = load_score_history()

    regressions = []
    for skill_name, skill_history in history.items():
        if skill_history.trend == "regression":
            regressions.append(skill_history)

    if not regressions:
        print("\n✓ No regressions detected!")
        return 0

    regressions.sort(key=lambda x: x.delta)

    print(f"\n{'=' * 70}")
    print(f" Regression Report ({len(regressions)} skills)")
    print(f"{'=' * 70}")
    print(f"{'Skill':<30} {'Previous':<10} {'Current':<10} {'Delta':<10}")
    print("-" * 70)

    for sh in regressions:
        print(
            f"{sh.skill_name:<30} {sh.previous_score:<10} "
            f"{sh.latest_score:<10} {sh.delta:<+10}"
        )

    print("-" * 70)
    print("\nTo investigate regressions:")
    for sh in regressions:
        print(f"  python score_history.py --trend {sh.skill_name}")

    return 1


def show_report():
    """Show full score history report."""
    history = load_score_history()

    if not history:
        print("No score history recorded yet.")
        print("Run 'python score_history.py --record' to record scores.")
        return 0

    # Categorize skills
    improving = []
    stable = []
    regressions = []
    no_history = []

    for skill_name, skill_history in history.items():
        if not skill_history.entries:
            no_history.append(skill_name)
        elif skill_history.trend == "improving":
            improving.append(skill_history)
        elif skill_history.trend == "regression":
            regressions.append(skill_history)
        else:
            stable.append(skill_history)

    print(f"\n{'=' * 70}")
    print(f" Score History Report")
    print(f"{'=' * 70}")
    print(f"Total tracked skills: {len(history)}")
    print(f"  Improving: {len(improving)}")
    print(f"  Stable: {len(stable)}")
    print(f"  Regressions: {len(regressions)}")
    print(f"  No recent data: {len(no_history)}")

    if improving:
        print(f"\n{'=' * 70}")
        print(f" Improving ({len(improving)})")
        print(f"{'=' * 70}")
        improving.sort(key=lambda x: x.delta, reverse=True)
        for sh in improving[:10]:  # Top 10
            print(f"  {sh.skill_name:<30} {sh.previous_score:<6} → {sh.latest_score} ({sh.delta:+d})")

    if regressions:
        print(f"\n{'=' * 70}")
        print(f" Regressions ({len(regressions)}) - ACTION REQUIRED")
        print(f"{'=' * 70}")
        regressions.sort(key=lambda x: x.delta)
        for sh in regressions:
            print(f"  {sh.skill_name:<30} {sh.previous_score:<6} → {sh.latest_score} ({sh.delta:+d})")

    if stable:
        print(f"\n{'=' * 70}")
        print(f" Stable ({len(stable)})")
        print(f"{'=' * 70}")
        for sh in stable:
            print(f"  {sh.skill_name:<30} {sh.latest_score}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Skill Manager - Score History Tracking"
    )
    parser.add_argument(
        "--record", "-r", action="store_true", help="Record current scores"
    )
    parser.add_argument(
        "--trend", "-t", type=str, help="Show trend for specific skill"
    )
    parser.add_argument(
        "--regressions", action="store_true", help="Show all regressions"
    )
    parser.add_argument(
        "--report", action="store_true", help="Show full history report"
    )

    args = parser.parse_args()

    # No arguments = show help
    if not any([args.record, args.trend, args.regressions, args.report]):
        parser.print_help()
        print("\nExamples:")
        print("  python score_history.py --record       # Record scores now")
        print("  python score_history.py --trend <name>  # Show trend")
        print("  python score_history.py --regressions  # Show regressions")
        print("  python score_history.py --report       # Full report")
        return 0

    if args.record:
        return record_scores()
    elif args.trend:
        return show_trend(args.trend)
    elif args.regressions:
        return show_regressions()
    elif args.report:
        return show_report()

    return 0


if __name__ == "__main__":
    sys.exit(main())