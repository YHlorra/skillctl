import os
import sys
import yaml
import json
import subprocess
import concurrent.futures

def get_remote_hash(url):
    """Fetch the latest commit hash from the remote repository."""
    try:
        # Using git ls-remote to avoid downloading the whole repo
        # Asking for HEAD specifically
        result = subprocess.run(
            ['git', 'ls-remote', url, 'HEAD'], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        if result.returncode != 0:
            return None
        # Output format: <hash>\tHEAD
        parts = result.stdout.split()
        if parts:
            return parts[0]
        return None
    except Exception:
        return None

def scan_skills(skills_root):
    """Scan all subdirectories for SKILL.md and extract metadata."""
    skill_list = []
    
    if not os.path.exists(skills_root):
        print(f"Skills root not found: {skills_root}", file=sys.stderr)
        return []

    for item in os.listdir(skills_root):
        skill_dir = os.path.join(skills_root, item)
        if not os.path.isdir(skill_dir):
            continue
            
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            continue
            
        # Parse Frontmatter
        try:
            with open(skill_md, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Extract YAML between first two ---
            parts = content.split('---')
            if len(parts) < 3:
                continue # Invalid format
                
            frontmatter = yaml.safe_load(parts[1])
            
            # Check if managed by github-to-skills
            if 'github_url' in frontmatter:
                skill_list.append({
                    "name": frontmatter.get('name', item),
                    "dir": skill_dir,
                    "github_url": frontmatter['github_url'],
                    "local_hash": frontmatter.get('github_hash', 'unknown'),
                    "local_version": frontmatter.get('version', '0.0.0')
                })
        except Exception as e:
            # print(f"Skipping {item}: {e}", file=sys.stderr)
            pass
            
    return skill_list

def check_updates(skills):
    """Check for updates concurrently."""
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Create a map of future -> skill
        future_to_skill = {
            executor.submit(get_remote_hash, skill['github_url']): skill 
            for skill in skills
        }
        
        for future in concurrent.futures.as_completed(future_to_skill):
            skill = future_to_skill[future]
            try:
                remote_hash = future.result()
                skill['remote_hash'] = remote_hash
                
                if not remote_hash:
                    skill['status'] = 'error'
                    skill['message'] = 'Could not reach remote'
                elif remote_hash != skill['local_hash']:
                    skill['status'] = 'outdated'
                    skill['message'] = 'New commits available'
                else:
                    skill['status'] = 'current'
                    skill['message'] = 'Up to date'
                    
                results.append(skill)
            except Exception as e:
                skill['status'] = 'error'
                skill['message'] = str(e)
                results.append(skill)
                
    return results

if __name__ == "__main__":
    target_dir: str | None = None

    if len(sys.argv) >= 2:
        target_dir = sys.argv[1]

    if not target_dir:
        # 1. SKILLCTL_AGENT_DIR env var
        env_dir = os.environ.get("SKILLCTL_AGENT_DIR")
        if env_dir:
            target_dir = env_dir

    if not target_dir:
        # 2. user.json scan_paths[0] (or first global)
        try:
            from user_config import resolve_agent_skills_dir
            resolved = resolve_agent_skills_dir()
            if resolved is not None:
                target_dir = str(resolved)
        except ImportError:
            pass

    if not target_dir:
        # 3. Generic default — same on every machine
        target_dir = os.path.expanduser("~/.claude/skills")
        print(
            f"Warning: no SKILLCTL_AGENT_DIR or user.json configured; "
            f"using generic default {target_dir}. "
            f"See references/user-config.md to override.",
            file=sys.stderr,
        )

    skills = scan_skills(target_dir)
    updates = check_updates(skills)

    print(json.dumps(updates, indent=2))

    skills = scan_skills(target_dir)
    updates = check_updates(skills)
    
    print(json.dumps(updates, indent=2))
