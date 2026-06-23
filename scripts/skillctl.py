#!/usr/bin/env python3
"""
skillctl v3.0 - 统一 CLI 入口

包装 18 个离散 Python 脚本为单一 CLI。旧脚本一行不动。
详细设计见 ../DESIGN.md。
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(
    os.environ.get("SKILLCTL_SCRIPTS_DIR", str(Path(__file__).resolve().parent))
).expanduser().resolve()
# SKILLCTL_ROOT 默认跟 SCRIPTS_DIR 同级；可通过环境变量覆盖
SKILLCTL_ROOT = Path(
    os.environ.get("SKILLCTL_ROOT", str(SCRIPTS_DIR.parent))
).expanduser().resolve()

# 命令 → 脚本映射（None 表示内置）
COMMANDS = {
    "init":     None,  # 内置
    "scan":     "scan_and_index.py",
    "install":  "scan_and_index.py",  # git clone <url> as parent wrapper
    "list":     "list_skills.py",
    "adopt":    "adopt_skills.py",
    "link":     "collect_and_link.py",
    "dedup":    "deduplicate.py",
    "delete":   "delete_skill.py",
    "update":   "check_updates.py",
    "validate": "governance_validate.py",
    "cleanup":  "cleanup.py",
    "migrate":  "migrate_nested_to_main.py",
    "library":  "skill_library.py",
    "rollback": "git_rollback.py",
    "score":    "score.py",
    "map":      "map_skills.py",
    "state":    "state.py",
    "toggle":   "toggle.py",
    "cull":       "cull.py",
    "remediate":  "remediate.py",
    "status":   None,  # 内置：聚合
    "help":     None,  # 内置
}

# 透传给业务脚本的全局 flag（CLI 内部不消费，业务脚本 argparse 处理）
PASSTHROUGH_FLAGS = {
    "--config", "--index", "--target", "--source", "--library",
    "--json", "--yes", "--dry-run", "--verbose", "--quiet",
    "--backup", "--rebuild-index", "--analyze", "--fetch", "--fix",
    "--skill", "--skills", "--path", "--scan-path", "--strategy",
    "--to", "--remove", "--strict", "--filter", "--execute",
    "--format", "--output", "--threshold", "--interactive",
    "--category", "--categories", "--no-stats", "--width",
    "--install", "--repos", "--reinstall", "--timeout",
}

# CLI 内部消费的 flag（业务脚本不接收）
INTERNAL_FLAGS = {"--skillctl-root", "--no-color"}


def find_config() -> Path:
    """定位 scan-config.yaml，优先级：环境变量 → skillctl_root → 当前目录"""
    env = os.environ.get("SKILLCTL_CONFIG")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    default = SKILLCTL_ROOT / "scan-config.yaml"
    return default if default.exists() else Path("scan-config.yaml")


def find_index() -> Path:
    """定位 index.json"""
    env = os.environ.get("SKILLCTL_INDEX")
    if env:
        return Path(env).expanduser()
    return SKILLCTL_ROOT / "index.json"


def run_script(script_name: str, args: list[str], verbose: bool = False) -> int:
    """subprocess 调用业务脚本，返回 exit code"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"[skillctl] error: script not found: {script_name}", file=sys.stderr)
        return 127

    # 自动注入 --index（仅限 argparse 定义了 --index 的脚本）
    idx = find_index()
    needs_index = {
        "list_skills.py", "deduplicate.py", "collect_and_link.py",
    }
    has_index = "--index" in args or "-i" in args
    auto_args = []
    if script_name in needs_index and not has_index and idx.exists():
        auto_args = ["--index", str(idx)]

    full = [sys.executable, str(script_path)] + auto_args + args
    if verbose:
        print(f"[skillctl] $ {' '.join(full)}", file=sys.stderr)
    result = subprocess.run(full, cwd=SKILLCTL_ROOT)
    return result.returncode


def split_args(args: list[str]) -> tuple[list[str], list[str]]:
    """把 argv 拆分为 passthrough + unknown。CLI 内部消费的已由 argparse 剔除。"""
    passthrough = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in PASSTHROUGH_FLAGS or a in INTERNAL_FLAGS:
            passthrough.append(a)
            # 一些 flag 接受 value（--config X / --path Y）
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                # 仅当 flag 在 likely-with-value 集合里
                if a in {"--config", "--index", "--target", "--source", "--library",
                         "--backup", "--skill", "--skills", "--path", "--scan-path",
                         "--strategy", "--to", "--format", "--output", "--filter",
                         "--threshold"}:
                    passthrough.append(args[i + 1])
                    i += 1
        else:
            # 未知 flag 也透传（业务脚本可能扩展了 flag）
            passthrough.append(a)
        i += 1
    return passthrough, []


def cmd_init(args) -> int:
    """内置 init：建立 .skillctl/ 目录与占位文件"""
    target = SKILLCTL_ROOT / ".skillctl"
    target.mkdir(parents=True, exist_ok=True)
    state_file = target / "state.json"
    if not state_file.exists():
        state_file.write_text(
            json.dumps(
                {
                    "version": "4.0",
                    "created_at": datetime.now().isoformat(),
                    "skills": {},
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    print(f"[skillctl] initialized at {target}")
    print(f"[skillctl] state file: {state_file}")
    return 0


def cmd_status(args) -> int:
    """内置 status：聚合多源信息，< 1 秒返回"""
    cfg = find_config()
    idx = find_index()
    state_file = SKILLCTL_ROOT / ".omc" / "state" / "last-tool-error.json"

    out = {
        "skillctl_version": "3.0",
        "config": str(cfg),
        "config_exists": cfg.exists(),
        "index": str(idx),
        "index_exists": idx.exists(),
        "last_tool_error": None,
    }

    if idx.exists():
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
            # 双向兼容：v3.0 字段（meta.*）优先，回退 v2.1（scan_time + stats.*）
            meta = data.get("meta")
            stats = data.get("stats", {})
            out["index_meta"] = {
                "last_scan_at": (
                    (meta or {}).get("last_scan_at")
                    or data.get("scan_time")
                ),
                "total_skills": (
                    (meta or {}).get("total_skills")
                    or stats.get("total_skills")
                ),
                "managed_count": (
                    (meta or {}).get("managed_count")
                    or stats.get("managed_count")
                ),
                "unmanaged_count": (
                    (meta or {}).get("unmanaged_count")
                    or stats.get("unmanaged_count")
                ),
                "duplicates": (
                    (meta or {}).get("duplicates")
                    or stats.get("duplicates")
                ),
                "schema_version": data.get("version"),
            }
        except (json.JSONDecodeError, OSError) as e:
            out["index_error"] = str(e)

    if state_file.exists():
        try:
            out["last_tool_error"] = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_help(args) -> int:
    """内置 help：列出所有命令 + 全局 flag"""
    import io
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    print("skillctl v3.0 - 统一 CLI\n", file=out)
    print("Usage: skillctl <command> [options]\n", file=out)
    print("Commands:", file=out)
    for cmd in COMMANDS:
        script = COMMANDS[cmd]
        if script:
            print(f"  {cmd:<10} -> {script}", file=out)
        else:
            print(f"  {cmd:<10} (built-in)", file=out)
    print("\nGlobal flags:", file=out)
    for f in sorted(PASSTHROUGH_FLAGS):
        print(f"  {f}", file=out)
    print("\nExamples:", file=out)
    print("  skillctl scan --config scan-config.yaml", file=out)
    print("  skillctl list --filter agent-reach", file=out)
    print("  skillctl adopt --dry-run", file=out)
    print("  skillctl status", file=out)
    out.flush()
    return 0


def main(argv: list[str] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        cmd_help([])
        return 0

    # 第一个非 flag token 是子命令
    cmd = None
    cmd_idx = None
    for i, a in enumerate(argv):
        if not a.startswith("-"):
            cmd = a
            cmd_idx = i
            break

    # 顶层 -h/--help 且无子命令 → 内置 help
    if cmd is None and argv[0] in ("-h", "--help"):
        return cmd_help([])

    if cmd is None:
        print("[skillctl] error: missing command. Try `skillctl help`", file=sys.stderr)
        return 2

    if cmd not in COMMANDS:
        print(f"[skillctl] error: unknown command '{cmd}'. Try `skillctl help`", file=sys.stderr)
        return 2

    rest = argv[cmd_idx + 1:]
    # 业务子命令后的 -h/--help 必须透传（业务脚本 argparse 自己处理）
    # 顶层 verbose flag（-v/--verbose）也透传
    verbose = "-v" in rest or "--verbose" in rest

    if cmd == "help":
        return cmd_help(rest)
    if cmd == "init":
        return cmd_init(rest)
    if cmd == "status":
        return cmd_status(rest)

    # 业务命令：subprocess 透传
    script = COMMANDS[cmd]
    passthrough, _ = split_args(rest)

    # Special transform: `skillctl install <url>` → scan_and_index.py wants `--install <url>` flag form
    if cmd == "install":
        # If user didn't already pass --install explicitly, prepend it to the first non-flag arg
        if "--install" not in passthrough and "-i" not in passthrough:
            # Find first positional (non-flag) arg as the URL
            url = None
            for a in rest:
                if not a.startswith("-"):
                    url = a
                    break
            if url:
                passthrough = ["--install", url] + [
                    a for a in passthrough if a != url
                ]

    return run_script(script, passthrough, verbose=verbose)


if __name__ == "__main__":
    sys.exit(main())
