# CLI 完整规范 (v5.0)

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
| `--library PATH` | �?| library 根目录（update --repos 用）|
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
  "skillctl_version": "4.0",
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
skillctl scan --enrich                              # GitHub API 推理 orphan skill 的 github_url
```

指向 `scan_and_index.py`。扫描多个目录，构建 `index.json`。`--enrich` 通过 GitHub API 推理 orphan skill 的 `github_url`（仅在 `--enrich` 时联网，默认关闭）。
### install

```bash
skillctl install <github-url>             # 克隆�?<library>/<repo-name>/ 保留 .git
skillctl install <url> --reinstall        # 冲突时备份工作树�?in-place 刷新
```

指向 `scan_and_index.py --install`。
v5+ Gate 流程：克隆到临时目录 → Gate 1 validate --strict → Gate 2 score（信息性，永不阻止）→ 用户确认（--non-interactive 自动）→ 原子移动到库。

| Flag | 说明 |
|------|------|
| `--reinstall` | 目标路径已存在时启用；备份现有工作树（不含 `.git/`）到 `<library>/.skillctl-backup/<ts>/<repo>/`，再 `git fetch && git reset --hard origin/HEAD` 原地刷新 |
| `--gate-mode enforce|skip` | 默认 enforce；skip 跳过 2-gate 验证 |
| `--no-gate` | 等效于 --gate-mode skip（带警告）|
| `--non-interactive` | gate 通过后自动确认，不提示用户 |

**已知限制**

- 不支持带 submodules 的仓库（v1 限制）
- 备份不含 `.git/`（从 remote 可重新拉取，避免 Windows 文件锁问题）


### list

```bash
skillctl list [--path <library>] [--filter NAME] [--info]
```

�?`list_skills.py`。从 index 或目录列�?skills�?
**注意**：`list` **不支�?`--json`**（业务脚本未实现）。要 JSON �?`status`�?
### adopt

```bash
skillctl adopt --dry-run                          # 预览
skillctl adopt --source <dir> --library <dir>    # 指定源和目标
skillctl adopt --yes --backup <dir> --rebuild-index  # 正式采纳
```

指向 `adopt_skills.py`。发现源目录（默认 `~/.claude/skills/`）中未托管的 skill，复制到 library，再将源替换为 junction（Windows）或 symlink（Unix），指向 library 中的目标位置。
v5+ Gate：每个 skill 在采纳前必须通过 2-gate 验证（validate --strict + score）。Gate 失败则跳过该 skill（不影响其他）。

| Flag | 说明 |
|------|------|
| `--dry-run` | 预览模式，不执行任何移动/复制/链接操作 |
| `--yes` | 跳过交互确认（v5：仅跳过 gate 后的确认，不跳过 gates 本身）|
| `--non-interactive` | gate 通过后自动确认，不提示用户（CI / agent 用）|
| `--no-gate` | 跳过 2-gate 验证（NOT 推荐）|
| `--gate-mode enforce|skip` | 默认 enforce |
| `--backup DIR` | 采纳前将原始源目录备份到此目录 |
| `--rebuild-index` | 采纳完成后运行 scan 刷新 index.json |
| `--source PATH` | 源目录（默认 `~/.claude/skills/`） |
| `--library PATH` | 目标 library 根目录（默认 SKILL_LIBRARY_PATH 或 user.json） |


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

指向 `migrate_nested_to_main.py`。嵌套 Git repo 中的 skills 迁到主库。
v5+ Gate：每个嵌套 skill 在移动前必须通过 2-gate 验证。Gate 失败则跳过该 skill（不影响其他）。

| Flag | 说明 |
|------|------|
| `--dry-run` | 预览模式（gate 仍然运行以供查看）|
| `--execute` | 实际执行迁移 |
| `--non-interactive` | gate 通过后自动确认，不提示用户 |
| `--no-gate` | 跳过 2-gate 验证（NOT 推荐）|
| `--gate-mode enforce|skip` | 默认 enforce |


### score

```bash
skillctl score                          # Darwin 8维评分
skillctl score track                    # 记录当前分数到历史
skillctl score trend <name>            # 显示 skill 评分趋势
skillctl score regressions              # 列出分数下降的 skill
skillctl score history-report           # 完整历史报告
```

指向 `score.py`（评分）和 `score_history.py`（历史追踪）。
`score` 本身运行 Darwin 评分；子命令路由到 `score_history.py` 的对应模式。
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
- `2` CLI 参数错误（未知命令 / 缺命令）
- `3` Gate 报告已输出，用户拒绝确认（仅交互模式）
- `4` Gate 失败（install：任意 skill 未通过 gate；adopt/migrate：所有候选 skill 均未通过 gate）
- `127` 业务脚本不存在
