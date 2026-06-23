#!/usr/bin/env python3
"""
Skill Manager - Skill Library Module

Centralized skill library architecture:
- All skills stored in one library location
- Global skills symlinked from library to ~/.claude/skills/
- Project skills symlinked from library to project .claude/skills/

Benefits:
- Single source of truth for all skills
- Easy mass updates (update once in library)
- Disk space efficient (no duplicates via symlinks)
- Clear provenance tracking
"""

import os
import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Union
import subprocess

# Force UTF-8 encoding for stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Library config file name
LIBRARY_CONFIG_FILE = ".skill-library.json"


def expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in path."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def is_symlink(path: Path) -> bool:
    """Check if path is a symlink (works on Windows too)."""
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


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def create_symlink(source: Path, link: Path) -> bool:
    """Create a symlink from link to source. Works on Windows and Unix."""
    try:
        link.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing symlink or file if present
        if link.exists() or is_symlink(link):
            if is_symlink(link):
                link.unlink()
            elif link.is_dir() and not is_symlink(link):
                print(f"  Warning: {link} is a real directory, skipping")
                return False
            else:
                link.unlink()

        # Create symlink
        if is_windows():
            if source.is_dir():
                try:
                    os.symlink(str(source), str(link), target_is_directory=True)
                except OSError:
                    # Fallback: use junction on Windows
                    subprocess.run(
                        ["cmd", "/c", "mklink", "/J", str(link), str(source)],
                        shell=True,
                        check=True,
                        capture_output=True,
                    )
            else:
                os.symlink(str(source), str(link))
        else:
            os.symlink(str(source), str(link))

        print(f"  Created symlink: {link} -> {source}")
        return True
    except Exception as e:
        print(f"  Error creating symlink: {e}")
        return False


def remove_symlink(path: Path) -> bool:
    """Remove a symlink (works on both Windows and Unix)."""
    try:
        if is_symlink(path):
            if path.is_dir() or (is_windows() and not path.is_file()):
                os.rmdir(path)
            else:
                path.unlink()
            return True
    except Exception as e:
        print(f"  Error removing symlink {path}: {e}")
    return False


class SkillLibrary:
    """
    Manages a centralized skill library with symlink-based distribution.

    Library structure:
    - /path/to/library/          (e.g., ~/skill-library)
      ├── skill-a/
      ├── skill-b/
      └── .skill-library.json   (library config)

    Symlinks created:
    - Global: /~/.claude/skills/skill-a -> /path/to/library/skill-a
    - Project: /project/.claude/skills/skill-a -> /path/to/library/skill-a
    """

    def __init__(self, library_path: Optional[Path] = None):
        """
        Initialize skill library manager.

        Args:
            library_path: Path to the skill library. If None, discovers or creates default.
        """
        if library_path:
            self.library_path = expand_path(str(library_path))
        else:
            # Try to discover existing library or create default
            self.library_path = self._discover_or_create_library()

        self.config = self._load_config()

    def _discover_or_create_library(self) -> Path:
        """Discover existing library or create default."""
        # Check common locations
        candidates = [
            Path.home() / "skill-library",
            Path.home() / ".skill-library",
            Path.home() / "skills" / "library",
        ]

        for candidate in candidates:
            config_path = candidate / LIBRARY_CONFIG_FILE
            if config_path.exists():
                print(f"Discovered skill library at: {candidate}")
                return candidate

        # Create default
        default_path = Path.home() / "skill-library"
        print(f"No skill library found. Creating at: {default_path}")
        default_path.mkdir(parents=True, exist_ok=True)
        return default_path

    def _load_config(self) -> dict:
        """Load or create library configuration."""
        config_path = self.library_path / LIBRARY_CONFIG_FILE
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)

        # Create default config
        config = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "library_path": str(self.library_path),
            "global_skills_link": str(Path.home() / ".claude" / "skills"),
            "skills": {},
        }
        self._save_config(config)
        return config

    def _save_config(self, config: dict = None):
        """Save library configuration."""
        if config is None:
            config = self.config
        config_path = self.library_path / LIBRARY_CONFIG_FILE
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Library config saved: {config_path}")

    def initialize(self, global_skills_link: Optional[Path] = None) -> dict:
        """
        LIB-01: Initialize the skill library.

        Args:
            global_skills_link: Path where global skills should be symlinked
                               (default: ~/.claude/skills)

        Returns:
            Initialization result dict
        """
        if global_skills_link is None:
            global_skills_link = Path.home() / ".claude" / "skills"

        global_skills_link = expand_path(str(global_skills_link))

        # Update config
        self.config["global_skills_link"] = str(global_skills_link)
        self.config["initialized_at"] = datetime.now().isoformat()
        self._save_config()

        # Create global skills symlink directory
        global_skills_link.mkdir(parents=True, exist_ok=True)

        print(f"\n✓ Skill library initialized at: {self.library_path}")
        print(f"  Global skills symlink location: {global_skills_link}")
        print(f"  Add skills to library using: skillctl library add <skill-path>")

        return {
            "success": True,
            "library_path": str(self.library_path),
            "global_skills_link": str(global_skills_link),
        }

    def add_skill(self, skill_source: Path, skill_name: str = None) -> dict:
        """
        Add a skill to the library.

        Args:
            skill_source: Path to the skill directory or SKILL.md
            skill_name: Optional name override

        Returns:
            Result dict
        """
        skill_source = expand_path(str(skill_source))

        # Find SKILL.md if directory given
        if skill_source.is_dir():
            skill_md = skill_source / "SKILL.md"
            if not skill_md.exists():
                return {"success": False, "error": f"No SKILL.md found in {skill_source}"}
            # Use directory name as skill name
            skill_name = skill_name or skill_source.name
        else:
            # It's a SKILL.md file
            skill_md = skill_source
            skill_source = skill_md.parent
            skill_name = skill_name or skill_source.name

        target_dir = self.library_path / skill_name

        if target_dir.exists():
            return {"success": False, "error": f"Skill '{skill_name}' already exists in library"}

        # Copy skill to library (preserve git for update tracking)
        try:
            if (skill_source / ".git").exists():
                subprocess.run(
                    ["git", "clone", str(skill_source), str(target_dir)],
                    capture_output=True,
                    check=True,
                )
                print(f"  Cloned with git history: {skill_source} -> {target_dir}")
            else:
                shutil.copytree(skill_source, target_dir, symlinks=False)
                print(f"  Copied: {skill_source} -> {target_dir}")

            # Update config
            self.config["skills"][skill_name] = {
                "added_at": datetime.now().isoformat(),
                "source_path": str(skill_source),
                "library_path": str(target_dir),
            }
            self._save_config()

            return {"success": True, "skill_name": skill_name, "path": str(target_dir)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def link_global_skills(self, skills: List[str] = None) -> dict:
        """
        LIB-02: Create symlinks for global skills from library to ~/.claude/skills/.

        Args:
            skills: List of skill names to link. If None, link all.

        Returns:
            Result dict with links created
        """
        global_link_path = expand_path(self.config["global_skills_link"])
        global_link_path.mkdir(parents=True, exist_ok=True)

        if skills is None:
            skills = list(self.config["skills"].keys())

        results = {"linked": [], "failed": []}

        for skill_name in skills:
            if skill_name not in self.config["skills"]:
                print(f"  Skill '{skill_name}' not in library, skipping")
                results["failed"].append(skill_name)
                continue

            library_skill_path = self.library_path / skill_name
            global_skill_link = global_link_path / skill_name

            if not library_skill_path.exists():
                print(f"  Skill '{skill_name}' not found in library, skipping")
                results["failed"].append(skill_name)
                continue

            if create_symlink(library_skill_path, global_skill_link):
                results["linked"].append(skill_name)
            else:
                results["failed"].append(skill_name)

        return results

    def link_project_skills(self, project_path: Path, skills: List[str] = None) -> dict:
        """
        LIB-02: Create symlinks for project-level skills from library to project/.claude/skills/.

        Args:
            project_path: Path to the project root
            skills: List of skill names to link. If None, link all.

        Returns:
            Result dict with links created
        """
        project_path = expand_path(str(project_path))
        project_skills_path = project_path / ".claude" / "skills"
        project_skills_path.mkdir(parents=True, exist_ok=True)

        if skills is None:
            skills = list(self.config["skills"].keys())

        results = {"linked": [], "failed": [], "project_path": str(project_skills_path)}

        for skill_name in skills:
            if skill_name not in self.config["skills"]:
                print(f"  Skill '{skill_name}' not in library, skipping")
                results["failed"].append(skill_name)
                continue

            library_skill_path = self.library_path / skill_name
            project_skill_link = project_skills_path / skill_name

            if not library_skill_path.exists():
                print(f"  Skill '{skill_name}' not found in library, skipping")
                results["failed"].append(skill_name)
                continue

            if create_symlink(library_skill_path, project_skill_link):
                results["linked"].append(skill_name)
            else:
                results["failed"].append(skill_name)

        return results

    def list_skills(self) -> List[dict]:
        """
        LIB-03: List all skills in the library.

        Returns:
            List of skill info dicts
        """
        skills = []
        for skill_name, skill_info in self.config["skills"].items():
            skill_path = self.library_path / skill_name
            has_git = (skill_path / ".git").exists() if skill_path.exists() else False
            skills.append({
                "name": skill_name,
                "added_at": skill_info.get("added_at"),
                "source_path": skill_info.get("source_path"),
                "has_git": has_git,
            })
        return skills

    def discover(self) -> dict:
        """
        LIB-03: Discover library and return info.

        Returns:
            Discovery result dict
        """
        return {
            "library_path": str(self.library_path),
            "config_exists": (self.library_path / LIBRARY_CONFIG_FILE).exists(),
            "skill_count": len(self.config["skills"]),
            "skills": list(self.config["skills"].keys()),
        }

    def register_skill(self, skill_source: Path, auto_link: str = None) -> dict:
        """
        LIB-03: Register an existing skill to the library.

        Args:
            skill_source: Path to existing skill (directory or SKILL.md)
            auto_link: Optional link type - "global" or "project" to auto-link after registering

        Returns:
            Result dict
        """
        skill_source = expand_path(str(skill_source))

        # Find SKILL.md if directory given
        if skill_source.is_dir():
            skill_md = skill_source / "SKILL.md"
            if not skill_md.exists():
                return {"success": False, "error": f"No SKILL.md found in {skill_source}"}
            skill_name = skill_source.name
        else:
            # It's a SKILL.md file
            skill_md = skill_source
            skill_source = skill_md.parent
            skill_name = skill_source.name

        target_dir = self.library_path / skill_name

        if target_dir.exists():
            return {"success": False, "error": f"Skill '{skill_name}' already exists in library"}

        # Copy skill to library (preserve git for update tracking)
        try:
            if (skill_source / ".git").exists():
                subprocess.run(
                    ["git", "clone", str(skill_source), str(target_dir)],
                    capture_output=True,
                    check=True,
                )
                print(f"  Cloned with git history: {skill_source} -> {target_dir}")
            else:
                shutil.copytree(skill_source, target_dir, symlinks=False)
                print(f"  Copied: {skill_source} -> {target_dir}")

            # Update config
            self.config["skills"][skill_name] = {
                "added_at": datetime.now().isoformat(),
                "source_path": str(skill_source),
                "library_path": str(target_dir),
                "registered": True,
            }
            self._save_config()

            # Auto-link if requested
            linked = False
            if auto_link == "global":
                result = self.link_global_skills([skill_name])
                linked = skill_name in result.get("linked", [])
            elif auto_link:
                # Assume it's a project path
                result = self.link_project_skills(Path(auto_link), [skill_name])
                linked = skill_name in result.get("linked", [])

            return {
                "success": True,
                "skill_name": skill_name,
                "path": str(target_dir),
                "linked": linked,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync(self, link_type: str = "global", project_path: Path = None) -> dict:
        """
        LIB-02: Sync (recreate) symlinks for all library skills.

        Args:
            link_type: "global" or "project"
            project_path: Required if link_type is "project"

        Returns:
            Result dict with sync results
        """
        if link_type == "global":
            # Remove existing symlinks first
            global_link_path = expand_path(self.config["global_skills_link"])
            if global_link_path.exists():
                for item in global_link_path.iterdir():
                    if is_symlink(item):
                        remove_symlink(item)

            # Recreate all
            result = self.link_global_skills()
            return {
                "success": True,
                "type": "global",
                "linked": result["linked"],
                "failed": result["failed"],
            }

        elif link_type == "project":
            if not project_path:
                return {"success": False, "error": "Project path required for project sync"}

            project_path = expand_path(str(project_path))
            project_skills_path = project_path / ".claude" / "skills"

            # Remove existing symlinks first
            if project_skills_path.exists():
                for item in project_skills_path.iterdir():
                    if is_symlink(item):
                        remove_symlink(item)

            # Recreate all
            result = self.link_project_skills(project_path)
            return {
                "success": True,
                "type": "project",
                "project_path": str(project_skills_path),
                "linked": result["linked"],
                "failed": result["failed"],
            }

        return {"success": False, "error": f"Unknown link type: {link_type}"}

    def initialize_wizard(self) -> dict:
        """
        LIB-01: Interactive wizard for first-install initialization.

        Returns:
            Initialization result dict
        """
        print("\n=== Skill Library Initialization Wizard ===\n")

        # Get library path
        default_library = Path.home() / "skill-library"
        library_input = input(f"Library path [{default_library}]: ").strip()
        library_path = Path(os.path.expanduser(library_input)) if library_input else default_library

        # Get global skills link path
        default_global = Path.home() / ".claude" / "skills"
        global_input = input(f"Global skills symlink path [{default_global}]: ").strip()
        global_link = Path(os.path.expanduser(global_input)) if global_input else default_global

        # Create library
        library_path.mkdir(parents=True, exist_ok=True)
        self.library_path = library_path

        # Update config
        self.config["library_path"] = str(library_path)
        self.config["global_skills_link"] = str(global_link)
        self.config["initialized_at"] = datetime.now().isoformat()
        self.config["wizard_initialized"] = True
        self._save_config()

        # Create global symlink directory
        global_link.mkdir(parents=True, exist_ok=True)

        print(f"\n✓ Skill library initialized at: {library_path}")
        print(f"  Global skills symlink location: {global_link}")

        # Offer to scan existing skills
        scan_input = input("\nScan for existing skills in default locations? [y/N]: ").strip().lower()
        if scan_input == "y":
            # Scan common locations
            scan_paths = [
                Path.home() / ".claude" / "skills",
                Path.home() / ".agents" / "skills",
            ]
            found_skills = []
            for scan_path in scan_paths:
                if scan_path.exists() and scan_path != global_link:
                    for item in scan_path.iterdir():
                        if item.is_dir() and (item / "SKILL.md").exists():
                            found_skills.append(item)

            if found_skills:
                print(f"\nFound {len(found_skills)} existing skills:")
                for skill in found_skills:
                    print(f"  - {skill.name}")

                register_input = input("\nRegister these skills to the new library? [y/N]: ").strip().lower()
                if register_input == "y":
                    for skill in found_skills:
                        result = self.register_skill(skill, auto_link="global")
                        if result["success"]:
                            print(f"  ✓ Registered: {result['skill_name']}")
                        else:
                            print(f"  ✗ Failed: {result.get('error', 'unknown error')}")

        return {
            "success": True,
            "library_path": str(library_path),
            "global_skills_link": str(global_link),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Skill Library - Centralized skill management with symlinks"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize skill library")
    init_parser.add_argument(
        "--path", "-p", type=str, help="Library path (default: ~/skill-library)"
    )
    init_parser.add_argument(
        "--global-link", "-g", type=str, help="Global skills symlink path (default: ~/.claude/skills)"
    )
    init_parser.add_argument(
        "--wizard", "-w", action="store_true", help="Interactive first-install wizard"
    )

    # register command (LIB-03)
    register_parser = subparsers.add_parser("register", help="Register existing skill to library")
    register_parser.add_argument("skill_path", type=str, help="Path to skill directory or SKILL.md")
    register_parser.add_argument(
        "--global", "-g", action="store_true", help="Auto-link to global skills"
    )
    register_parser.add_argument(
        "--project", "-p", type=str, help="Auto-link to project skills"
    )

    # sync command (LIB-02)
    sync_parser = subparsers.add_parser("sync", help="Sync (recreate) symlinks")
    sync_parser.add_argument(
        "--global", "-g", action="store_true", help="Sync global symlinks"
    )
    sync_parser.add_argument(
        "--project", "-p", type=str, help="Sync project symlinks"
    )

    # add command
    add_parser = subparsers.add_parser("add", help="Add skill to library")
    add_parser.add_argument("skill_path", type=str, help="Path to skill directory or SKILL.md")
    add_parser.add_argument("--name", "-n", type=str, help="Skill name override")

    # link command
    link_parser = subparsers.add_parser("link", help="Create skill symlinks")
    link_parser.add_argument(
        "--global-link", "-g", action="store_true", help="Link global skills to ~/.claude/skills"
    )
    link_parser.add_argument(
        "--project", "-p", type=str, help="Link project skills to project/.claude/skills/"
    )
    link_parser.add_argument(
        "--skills", "-s", type=str, nargs="+", help="Specific skills to link (default: all)"
    )

    # list command
    subparsers.add_parser("list", help="List skills in library")

    # discover command
    subparsers.add_parser("discover", help="Discover existing library")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Initialize library with optional path
    if args.command == "init":
        if getattr(args, 'wizard', False):
            # Interactive wizard mode
            lib = SkillLibrary(expand_path(args.path) if args.path else None)
            result = lib.initialize_wizard()
            return 0 if result["success"] else 1

        lib = SkillLibrary(expand_path(args.path) if args.path else None)
        global_link = expand_path(args.global_link) if args.global_link else None
        result = lib.initialize(global_link)
        print(f"\n{'✓' if result['success'] else '✗'} Initialization complete")
        return 0 if result["success"] else 1

    # All other commands need an existing library
    lib = SkillLibrary()

    if args.command == "add":
        result = lib.add_skill(args.skill_path, args.name)
        if result["success"]:
            print(f"\n✓ Added '{result['skill_name']}' to library")
            # Auto-link to global if initialized
            if "initialized_at" in lib.config:
                link_result = lib.link_global_skills([result["skill_name"]])
                print(f"  Linked to global: {result['skill_name'] in link_result['linked']}")
        else:
            print(f"\n✗ Failed to add skill: {result['error']}")
        return 0 if result["success"] else 1

    elif args.command == "link":
        if args.global_link:
            result = lib.link_global_skills(args.skills)
            print(f"\nLinked {len(result['linked'])} skills to global")
        if args.project:
            result = lib.link_project_skills(expand_path(args.project), args.skills)
            print(f"\nLinked {len(result['linked'])} skills to project: {result['project_path']}")
        if not args.global_link and not args.project:
            print("Error: Specify --global or --project")
            return 1
        return 0

    elif args.command == "list":
        skills = lib.list_skills()
        if not skills:
            print("No skills in library. Run 'skillctl library add <skill-path>' first.")
            return 0
        print(f"\nSkills in library ({len(skills)}):")
        for skill in skills:
            git标记 = " [git]" if skill["has_git"] else ""
            print(f"  • {skill['name']}{git标记}")
        return 0

    elif args.command == "discover":
        info = lib.discover()
        print(f"\nSkill Library Discovery:")
        print(f"  Path: {info['library_path']}")
        print(f"  Config exists: {info['config_exists']}")
        print(f"  Skills count: {info['skill_count']}")
        if info['skills']:
            print(f"  Skills: {', '.join(info['skills'][:5])}{'...' if len(info['skills']) > 5 else ''}")
        return 0

    elif args.command == "register":
        auto_link = None
        if getattr(args, 'global', False):
            auto_link = "global"
        elif getattr(args, 'project', None):
            auto_link = args.project

        result = lib.register_skill(args.skill_path, auto_link=auto_link)
        if result["success"]:
            print(f"\n✓ Registered '{result['skill_name']}' to library")
            if result.get("linked"):
                print(f"  Auto-linked to: {auto_link}")
        else:
            print(f"\n✗ Failed to register: {result['error']}")
        return 0 if result["success"] else 1

    elif args.command == "sync":
        if getattr(args, 'global', False):
            result = lib.sync(link_type="global")
            if result["success"]:
                print(f"\n✓ Synced {len(result['linked'])} global symlinks")
                if result.get("failed"):
                    print(f"  Failed: {len(result['failed'])}")
            else:
                print(f"\n✗ Sync failed: {result.get('error', 'unknown error')}")
            return 0 if result["success"] else 1

        elif getattr(args, 'project', None):
            result = lib.sync(link_type="project", project_path=Path(args.project))
            if result["success"]:
                print(f"\n✓ Synced {len(result['linked'])} project symlinks")
                print(f"  Project: {result['project_path']}")
                if result.get("failed"):
                    print(f"  Failed: {len(result['failed'])}")
            else:
                print(f"\n✗ Sync failed: {result.get('error', 'unknown error')}")
            return 0 if result["success"] else 1

        else:
            print("Error: Specify --global or --project")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())