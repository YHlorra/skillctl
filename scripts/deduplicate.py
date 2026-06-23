#!/usr/bin/env python3
"""
Skill Manager - Deduplicate Module

检测重复的 skill，处理冲突，生成解决决策。
支持自动处理（global/local）或交互式询问用户。
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def is_symlink(path: Path) -> bool:
    """Check if path is a symlink."""
    try:
        return path.is_symlink()
    except OSError:
        return False


def resolve_symlink_target(path: Path) -> Path:
    """Resolve symlink to real path."""
    try:
        return path.resolve()
    except OSError:
        return path


def get_git_modified_time(path: Path) -> Optional[datetime]:
    """Get last modified time from git log for a directory."""
    try:
        import subprocess
        result = subprocess.run(
            ['git', '-C', str(path), 'log', '-1', '--format=%ct', '--', '.'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            timestamp = int(result.stdout.strip())
            return datetime.fromtimestamp(timestamp)
    except Exception:
        pass
    return None


def get_dir_modified_time(path: Path) -> datetime:
    """Get directory last modified time."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return datetime.min


class Deduplicator:
    """Handles skill deduplication with conflict resolution."""

    def __init__(self, index_path: Path):
        self.index_path = index_path
        with open(index_path, 'r', encoding='utf-8') as f:
            self.index = json.load(f)
        self.decisions = {}
        self.resolved = []

    def analyze_conflict(self, dup_entry: dict) -> dict:
        """Analyze a duplicate entry and provide details for resolution."""
        name = dup_entry['name']
        instances = dup_entry['instances']
        real_instances = dup_entry.get('real_instances', [])

        # Get skill info
        skill = self.index['skills'].get(name)
        if not skill:
            return {'error': f'Skill {name} not found in index'}

        locations = skill['locations']

        # Categorize locations
        analysis = {
            'skill_name': name,
            'description': skill['metadata'].get('description', ''),
            'locations': [],
            'real_locations': [],
            'symlink_locations': [],
            'has_git': skill['git']['has_git'],
            'suggestion': None
        }

        for loc in locations:
            loc_info = {
                'path': loc['path'],
                'scope': loc['scope'],
                'priority': loc['priority'],
                'is_symlink': loc['is_symlink'],
                'real_path': loc.get('real_path', loc['path']),
                'modified': loc.get('modified')
            }

            if loc['is_symlink']:
                analysis['symlink_locations'].append(loc_info)
            else:
                analysis['real_locations'].append(loc_info)
                analysis['locations'].append(loc_info)

        # Auto-suggestion based on analysis
        if len(analysis['real_locations']) == 1:
            analysis['suggestion'] = analysis['real_locations'][0]['path']
            analysis['reason'] = 'Only one real location exists'
        elif len(analysis['real_locations']) > 1:
            # Find newest
            newest = max(analysis['real_locations'],
                        key=lambda x: x.get('modified') or '1970-01-01')
            analysis['suggestion'] = newest['path']
            analysis['reason'] = f'Newest modification: {newest.get("modified")}'
        else:
            # All are symlinks
            if analysis['symlink_locations']:
                real_symlinks = [l for l in analysis['symlink_locations']
                                if not is_symlink(expand_path(l['real_path']))]
                if real_symlinks:
                    analysis['suggestion'] = real_symlinks[0]['real_path']
                    analysis['reason'] = 'First real location found via symlink'

        return analysis

    def resolve_global_local(self, analysis: dict) -> str:
        """Auto-resolve by preferring global scope."""
        if not analysis['real_locations']:
            return analysis['locations'][0]['path'] if analysis['locations'] else None

        # Prefer global scope
        global_locs = [l for l in analysis['real_locations'] if l['scope'] == 'global']
        if global_locs:
            return global_locs[0]['path']

        # If no global, return first real location
        return analysis['real_locations'][0]['path']

    def resolve_local_first(self, analysis: dict) -> str:
        """Auto-resolve by preferring local/project scope."""
        if not analysis['real_locations']:
            return analysis['locations'][0]['path'] if analysis['locations'] else None

        # Prefer local scope
        local_locs = [l for l in analysis['real_locations'] if l['scope'] == 'local']
        if local_locs:
            return local_locs[0]['path']

        # If no local, return first real location
        return analysis['real_locations'][0]['path']

    def resolve_canonical(self, analysis: dict) -> str:
        """Auto-resolve by preferring the configured canonical library path.

        The canonical prefix is read from (in order):
          1. ``SKILLCTL_CANONICAL_PREFIX`` environment variable
          2. ``canonical_path`` in ``scan-config.yaml``
        If neither is set, falls back to the first real location.
        """
        if not analysis['real_locations']:
            return analysis['locations'][0]['path'] if analysis['locations'] else None

        canonical_prefix = os.environ.get("SKILLCTL_CANONICAL_PREFIX", "").strip()
        if not canonical_prefix:
            # Try to read from scan-config.yaml (best-effort, no hard dependency)
            try:
                import yaml  # type: ignore
                cfg_path = Path("scan-config.yaml")
                if cfg_path.is_file():
                    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                    canonical_prefix = str(cfg.get("canonical_path", "")).strip()
            except Exception:
                canonical_prefix = ""

        if canonical_prefix:
            canonical_locs = [
                l for l in analysis['real_locations']
                if canonical_prefix in l['path']
            ]
            if canonical_locs:
                return canonical_locs[0]['path']

        # Fallback: return first real location
        return analysis['real_locations'][0]['path']

    def interactive_resolve(self, analysis: dict) -> Optional[str]:
        """Interactively ask user to resolve conflict."""
        print(f"\n{'='*60}")
        print(f"Conflict: {analysis['skill_name']}")
        print(f"Description: {analysis['description'][:80]}...")
        print(f"Git repository: {'Yes' if analysis['has_git'] else 'No'}")
        print(f"{'='*60}")

        real_locs = analysis['real_locations']
        for i, loc in enumerate(real_locs, 1):
            print(f"\n  [{i}] {loc['path']}")
            print(f"      Scope: {loc['scope']}, Priority: {loc['priority']}")
            print(f"      Modified: {loc.get('modified', 'unknown')}")

        if len(real_locs) == 1:
            print(f"\n  [K] Keep this one (only option)")
            print(f"  [Q] Quit and save decisions for later")
            choice = input("\n  Your choice (number/K/Q): ").strip().upper()
            if choice == 'K' or choice == str(1):
                return real_locs[0]['path']
            elif choice == 'Q':
                return None
        else:
            print(f"\n  [Q] Quit and save decisions for later")
            choice = input("\n  Select which to KEEP (number or Q): ").strip().upper()
            if choice.isdigit() and 1 <= int(choice) <= len(real_locs):
                return real_locs[int(choice) - 1]['path']
            elif choice == 'Q':
                return None

        return None

    def resolve_all(self, strategy: str = 'ask') -> dict:
        """Resolve all duplicates based on strategy."""
        duplicates = self.index.get('duplicates', [])

        if not duplicates:
            print("No duplicates found.")
            return {'decisions': {}, 'resolved': []}

        print(f"\nFound {len(duplicates)} duplicate(s)/conflict(s)")

        for dup in duplicates:
            analysis = self.analyze_conflict(dup)

            if 'error' in analysis:
                print(f"Error analyzing {dup['name']}: {analysis['error']}")
                continue

            decision = None

            if strategy == 'global':
                decision = self.resolve_global_local(analysis)
                reason = 'global_scope_preference'
            elif strategy == 'local':
                decision = self.resolve_local_first(analysis)
                reason = 'local_scope_preference'
            elif strategy == 'newest':
                if analysis['suggestion']:
                    decision = analysis['suggestion']
                    reason = 'newest_modification'
                else:
                    decision = analysis['locations'][0]['path']
                    reason = 'first_available'
            elif strategy == 'canonical':
                decision = self.resolve_canonical(analysis)
                reason = 'canonical_path_preference'
            else:  # 'ask'
                decision = self.interactive_resolve(analysis)
                reason = 'user_choice'

            if decision:
                self.decisions[dup['name']] = {
                    'keep': decision,
                    'reason': reason,
                    'resolved_at': datetime.now().isoformat()
                }
                self.resolved.append(dup['name'])

                # Find paths to remove
                all_paths = set(loc['path'] for loc in analysis['locations'])
                all_paths.discard(decision)
                self.decisions[dup['name']]['remove'] = list(all_paths)

                print(f"\n  → Keeping: {decision}")
            else:
                print(f"\n  → Skipped (user quit)")

        return {
            'decisions': self.decisions,
            'resolved': self.resolved,
            'skipped': len(duplicates) - len(self.resolved)
        }

    def save_decisions(self, output_path: Path = None, strategy: str = 'ask'):
        """Save resolution decisions to file."""
        output = output_path or Path(str(self.index_path).replace('.json', '_decisions.json'))

        decisions_output = {
            'generated_at': datetime.now().isoformat(),
            'strategy_used': strategy,
            'total_duplicates': len(self.index.get('duplicates', [])),
            'resolved_count': len(self.resolved),
            'decisions': self.decisions
        }

        with open(output, 'w', encoding='utf-8') as f:
            json.dump(decisions_output, f, indent=2, ensure_ascii=False)

        print(f"\nDecisions saved to: {output}")
        return output


def load_decisions(decisions_path: Path) -> dict:
    """Load previously saved decisions."""
    with open(decisions_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Resolve skill duplicates')
    parser.add_argument('--index', '-i', type=str, required=True,
                        help='Path to index.json from scan_and_index.py')
    parser.add_argument('--strategy', '-s', type=str, choices=['global', 'local', 'newest', 'canonical', 'ask'],
                        default='ask',
                        help='Resolution strategy: global (prefer global), local (prefer project), newest (most recent), canonical (prefer $SKILLCTL_CANONICAL_PREFIX), ask (interactive)')
    parser.add_argument('--output', '-o', type=str,
                        help='Output path for decisions file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')

    args = parser.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"Error: Index file not found: {index_path}")
        return 1

    deduplicator = Deduplicator(index_path)
    result = deduplicator.resolve_all(strategy=args.strategy)

    print(f"\n{'='*60}")
    print("Resolution Summary")
    print(f"{'='*60}")
    print(f"Total duplicates: {result['skipped'] + len(result['resolved'])}")
    print(f"Resolved: {len(result['resolved'])}")
    print(f"Skipped: {result['skipped']}")

    if result['resolved']:
        print(f"\nDecisions:")
        for name, decision in result['decisions'].items():
            print(f"  {name}:")
            print(f"    Keep: {decision['keep']}")
            print(f"    Remove: {', '.join(decision['remove'][:3])}{'...' if len(decision['remove']) > 3 else ''}")

    if not args.dry_run:
        decisions_path = deduplicator.save_decisions(Path(args.output) if args.output else None, strategy=args.strategy)
        print(f"\nDecisions file ready: {decisions_path}")
        print("Next step: Run collect_and_link.py with --decisions to apply changes")
    else:
        print("\nDry run - no changes saved")

    return 0


if __name__ == '__main__':
    sys.exit(main())
