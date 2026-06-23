# CLI 完整规范 (v3.0)

## 入口

```bash
python scripts/skillctl.py <command> [options]
```

或部署后�?
```bash
skillctl <command> [options]
```

## 全局 flag（透传�?
| Flag | 接受�?| 说明 |
|------|-------|------|
| `--config PATH` | �?| scan-config.yaml 路径 |
| `--index PATH` | �?| index.json 路径 |
| `--target PATH` | �?| 链接目标目录（link 用）|
| `--source PATH` | �?| 源目录（adopt 用）|
| `--library PATH` | �?| library 根目录（adopt 用）|
| `--path PATH` | �?| 扫描路径（list / cleanup 用）|
| `--json` | �?| 强制 JSON 输出（仅 update/validate/status 支持；list 不支持）|
| `--yes` | �?| 跳过交互确认 |
| `--dry-run` | �?| 预览模式 |
| `--verbose` | �?| 详细日志 |
| `--quiet` | �?| 静默 |
| `--backup DIR` | �?| 备份目录 |
| `--rebuild-index` | �?| scan 后重�?index |
| `--analyze` | �?| dedup 分析模式 |
| `--fetch` | �?| update �?fetch 远程 |
| `--fix` | �?| validate 自动修复 |
| `--strict` | �?| validate 严格模式 |
| `--skill NAME` | �?| 单个 skill �?|
| `--skills NAME1,NAME2` | �?| 多个 skill |
| `--filter PATTERN` | �?| list 过滤模式 |
| `--strategy MODE` | �?| dedup 策略 |
| `--to REF` | �?| rollback 目标 |
| `--remove` | �?| cleanup 实际删除 |
| `--scan-path PATH` | �?| cleanup 扫描路径 |
| `--execute` | �?| migrate 实际执行 |
| `--format FMT` | �?| 输出格式 |
| `--output PATH` | �?| 输出文件 |
| `--threshold N` | �?| 阈�?|
| `--interactive` | �?| dedup 交互模式 |

## 子命�?
### init

```bash
skillctl init
```

�?`<root>/.skillctl/` 目录�?`state.json` 占位文件。幂等�?
### status

```bash
skillctl status
```

聚合输出 JSON�?
```json
{
  "skillctl_version": "3.0",
  "config": "<skillctl_root>/scan-config.yaml",
  "config_exists": true,
  "index": "<skillctl_root>/index.json",
  "index_exists": true,
  "index_meta": {
    "last_scan_at": "2026-05-20T01:44:00",
    "total_skills": 87,
    "managed_count": 65,
    "unmanaged_count": 22
  },
  "last_tool_error": null
}
```

< 1 秒返回。不调业务脚本�?
### scan

```bash
skillctl scan --config scan-config.yaml [--rebuild-index]
```

�?`scan_and_index.py`。扫描多个目录，构建 `index.json`�?
### install

```bash
skillctl install <github-url>             # 克隆�?<library>/<repo-name>/ 保留 .git
skillctl install <url> --reinstall        # 冲突时备份工作树�?in-place 刷新
```

�?`scan_and_index.py --install`。把 GitHub 仓库克隆为带 `.git/` 的父 wrapper 目录，里面所�?`SKILL.md` 子目录随后由 `skillctl scan` 收进 index�?
**flag �?*

| Flag | 说明 |
|------|------|
| `--reinstall` | 目标路径已存在时启用；备份现有工作树（不�?`.git/`）到 `<library>/.skillctl-backup/<ts>/<repo>/`，再 `git fetch && git reset --hard origin/HEAD` 原地刷新 |

**已知限制**

- 不支持带 submodules 的仓库（v1 限制�?- 备份不含 `.git/`（从 remote 可重新拉取，避免 Windows 文件锁问题）

### list

```bash
skillctl list [--path <library>] [--filter NAME] [--info]
```

�?`list_skills.py`。从 index 或目录列�?skills�?
**注意**：`list` **不支�?`--json`**（业务脚本未实现）。要 JSON �?`status`�?
### adopt

```bash
skillctl adopt --dry-run        # 预览
skillctl adopt --yes --backup .skill-adopt-backup --rebuild-index
```

�?`adopt_skills.py`。将 `~/.claude/skills/` 未托�?skill 复制�?library，替换为 junction�?
### link

```bash
skillctl link --index index.json --target ~/.claude/skills --skills x-tweet-fetcher
```

�?`collect_and_link.py`。symlink/junction 链接到目标目录�?
### dedup

```bash
skillctl dedup --analyze        # 只分析不执行
skillctl dedup --strategy global  # 自动处理
skillctl dedup --interactive    # 询问用户
```

�?`deduplicate.py`�?
### delete

```bash
skillctl delete --skill <name> --yes --backup .delete-backup
```

�?`delete_skill.py`（旧 sys.argv 风格，CLI 内部包装�?argparse）�?
### update

```bash
skillctl update                       # 全部检查（基于 index.json �?per-skill 路径�?skillctl update --skill <name>        # 单个
skillctl update --fetch --json        # �?fetch 远程�?JSON 输出
skillctl update --repos               # 批量：扫 library_root 下每个直�?git 子目录，git pull --ff-only
skillctl update --repos --dry-run     # 列出哪些会被 pull，不实际执行
skillctl update --repos --library <p> # 指定 library 根（默认 SKILL_LIBRARY_PATH �?skillctl canonical�?skillctl update --repos --timeout 120 # �?repo 超时秒数（默�?60�?```

�?`check_updates.py`�?
`--repos` �?`--skill` 互斥。`--repos` 走文件系统遍历（不依�?index.json），所以同时覆盖：�?skill wrapper 仓库（`ljg-skills/`）、单 skill 自带 `.git` 的仓库（`hunt/`）、以�?`install` 创建�?wrapper。一�?repo 出错不影响其他�?
### validate

```bash
skillctl validate
skillctl validate --skill <name> --strict --json
```

�?`governance_validate.py`。SKILL.md 结构 + 安全扫描 + 红标检查�?
### cleanup

```bash
skillctl cleanup --dry-run                     # 预览
skillctl cleanup --remove --scan-path <path>   # 实际删除
```

�?`cleanup.py`。清理孤�?symlink / 空目�?/ 孤儿备份�?
### migrate

```bash
skillctl migrate --dry-run
skillctl migrate --execute
```

�?`migrate_nested_to_main.py`。嵌�?Git repo �?skills 迁到主库�?
### library

```bash
skillctl library --help
```

�?`skill_library.py`。集中式 library 管理�?
### score

```bash
skillctl score
```

�?`score.py`。Darwin 评分（内部用）�?
## 环境变量

| 变量 | 作用 |
|------|------|
| `SKILLCTL_CONFIG` | 默认 `--config` 路径 |
| `SKILLCTL_INDEX` | 默认 `--index` 路径 |
| `SKILLCTL_SCRIPTS_DIR` | 业务脚本目录（开发期覆盖）|
| `SKILLCTL_ROOT` | skillctl 根目录（开发期覆盖）|
| `SKILL_LIBRARY_PATH` | 库根目录（透传到各业务脚本）|

## Exit code

- `0` 成功
- `1` 业务错误
- `2` CLI 参数错误（未知命�?/ 缺命令）
- `127` 业务脚本不存�?