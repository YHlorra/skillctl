---
name: skillctl
alias: sk
description: 管理本地 Skills 库——扫描、索引、安装（含强制 2-gate 验证）、链接、列表、删除、去重、Git 更新检测、治理验证、迁移、清理、采纳。统一 CLI 入口 `python scripts/skillctl.py <command>`。
triggers: /skillctl、/sk、「管理skill」「扫描skill」「安装skill」「链接skill」「skill去重」「列出skill」「删除skill」「迁移skill」「清理skill」
scope: global
license: MIT
topics:
  - skill-management
  - lifecycle
  - sync
  - cli
compatibility:
  canonical_format: agent-skills
  adapters: [openai, claude, generic]
---

# sk - Skill Lifecycle Manager (v5.0)

统一 CLI 管理 Skills 生命周期。v5 强制 2-gate 协议：13 个路由命令 + init/status 两个内置 + help = 共 16 条。

## 意图路由表

**直接匹配下表，不要猜测命令名。** 如果用户意图不在表中，回退到 `skillctl help`。

| 用户意图（关键词） | 命令 | 示例 |
|---------------------|------|------|
| 扫描/发现/索引/重建 | `scan` | `skillctl scan --config scan-config.yaml` |
| 列出/查看/有哪些 | `list` | `skillctl list --json` |
| 从 GitHub 安装（含父目录 + git） | `install` | `skillctl install --non-interactive https://github.com/user/repo` |
| 链接到全局 | `link` | `skillctl link --skills X --target ~/.claude/skills` |
| 采纳/接收（本地 junction，含 gate） | `adopt` | `skillctl adopt --dry-run --non-interactive` |
| 去重/重复/冲突 | `dedup` | `skillctl dedup --dry-run` |
| 删除/移除 | `delete` | `skillctl delete --skill X --yes` |
| 更新/检测远程 | `update` | `skillctl update --fetch --skill X` 或 `skillctl update --repos --dry-run` |
| 验证/合规/治理 | `validate` | `skillctl validate --strict` |
| 清理/孤儿/过期 symlink | `cleanup` | `skillctl cleanup --dry-run` |
| 迁移/嵌套仓库（含 gate） | `migrate` | `skillctl migrate --dry-run --non-interactive` |
| 评分/排序 | `score` | `skillctl score` |
| 回滚/撤销 | `rollback` | `skillctl rollback --to HEAD~1` |
| 状态总览 | `status` | `skillctl status` |
| 初始化/首次 | `init` | `skillctl init` |
| 帮助/怎么用 | `help` | `skillctl help` |

## 三种安装范式

按数据源不同，`skillctl` 暴露三种把仓库纳入库的方式，**互不重叠，按场景选一种**：

| 范式 | 命令 | 物理布局 | 何时用 |
|------|------|----------|--------|
| **GitHub wrapper 安装** | `skillctl install <url>` | `<library>/<repo>/.git/ + skills/` | 远程仓库想保留 git 历史以便 `git pull` 更新 |
| **本地 junction 采纳** | `skillctl adopt` | `~/.claude/skills/<name>` → junction → `<library>/<name>` | `~/.claude/skills/` 下散落的本地 skill 想统一进库管理 |
| **迁移嵌套仓库到顶层** | `skillctl migrate` | `<library>/<name>/`（parent 保留） | 嵌套 repo 想把每个 skill 提取到顶层（不删 parent） |

`install` 和 `migrate` 是反操作：`install` 加 wrapper（嵌套），`migrate` 把 wrapper 里的 skill 拍平到顶层。两种布局 skillctl 都识别（`auto_detect_nested`），按用户偏好选。

## 边界

- **做**：扫描、索引、symlink、列表、删除、去重、Git 更新检测、治理验证、迁移、清理
- **不做**：skill 内容创作、跨机器同步、skill 内部逻辑修改

**安全边界（v5+）**：所有 L2 import 命令（install / adopt / migrate）在任何内容进入库之前，必须先通过 2-gate 验证（`validate --strict` + `score`）。Gate 失败则拒绝 import。可用 `--no-gate` 强制跳过（不推荐，仅限紧急情况）。

## 快速开始

```bash
python scripts/skillctl.py help         # 列出所有命令
python scripts/skillctl.py status       # 状态总览（< 1s）
python scripts/skillctl.py scan --config scan-config.yaml
python scripts/skillctl.py list --json
```

## 命令矩阵

### L1 Discover（只读，构造索引）

| 命令 | 用途 | 关键 flags |
|------|------|-----------|
| `init` | 初始化 .skillctl/ 目录 | — |
| `scan` | 扫描 + 重建 index.json | `--config` `--output` `--no-auto-nested` `--install <url>` |
| `list` | 列表 skills | `--path` `--index` `--filter` `--info` |
| `status` | 状态总览（JSON） | — |

### L2 Import（把 skill 纳入库）

| 命令 | 用途 | 关键 flags |
|------|------|-----------|
| `install` | 从 GitHub 克隆为 wrapper（保留 .git） | `<url>` `--reinstall` `--gate-mode` `--no-gate` `--non-interactive` |
| `adopt` | 采纳未托管 skill（junction，含 2-gate 验证） | `--dry-run` `--yes` `--backup` `--rebuild-index` `--source` `--library` `--gate-mode` `--no-gate` `--non-interactive` |
| `migrate` | 嵌套仓库 → 主库（含 2-gate 验证） | `--dry-run` `--execute` `--gate-mode` `--no-gate` `--non-interactive` |
| `link` | 链接到全局目录 | `--target` `--skills` `--dry-run` |

### L3 Maintain（组织、验证、同步）

| 命令 | 用途 | 关键 flags |
|------|------|-----------|
| `update` | 检测 Git 远程更新；`--repos` 批量刷新所有 wrapper | `--fetch` `--skill` `--repos` `--dry-run` `--library` `--json` |
| `dedup` | 检测 + 解决重复 | `--strategy` `--dry-run` `--output` |
| `validate` | 治理验证 | `--strict` `--fix` `--json` |
| `cleanup` | 清理孤儿 symlink | `--dry-run` `--remove` `--scan-path` |
| `score` | 内部评分 + 历史追踪 | `track` `trend <name>` `regressions` `history-report` |

### L4 Recover（删除、撤销）

| 命令 | 用途 | 关键 flags |
|------|------|-----------|
| `delete` | 删除 skill | `--yes` `--backup` |
| `rollback` | Git 撤销操作 | `--to` |
| `help` | 列出所有命令 | — |

## 全局 flag

业务脚本支持的 flag 因脚本而异，**调用 `skillctl <cmd> --help` 看实际清单**。常见的：

- `--config PATH` (scan / 多脚本)
- `--index PATH` (list / dedup 等)
- `--target PATH` (link)
- `--library PATH` (update --repos)
- `--dry-run` (adopt / link / dedup / cleanup / migrate)
- `--yes` (adopt / delete / dedup; v5: skips post-gate prompt only, not the gates themselves)
- `--backup DIR` (adopt / delete)
- `--filter PATTERN` (list)
- `--json` (update / validate 支持；list 不支持)
- `--gate-mode enforce|skip` (install / adopt / migrate; default `enforce`)
- `--no-gate` (install / adopt / migrate; bypass gates — NOT recommended)
- `--non-interactive` (install / adopt / migrate; auto-confirm on gate pass; for CI / agents)

`status` 命令固定输出 JSON。

## 工作流

### 标准流程（首次接入）

```bash
skillctl init
skillctl scan --config scan-config.yaml
skillctl list --json | head
```

### 写操作安全网

**adopt / link / delete / cleanup / migrate** 写操作前必须先 `--dry-run` 预览，确认无误后加 `--yes` 执行。建议带 `--backup` 留回滚点。

### 状态恢复

误操作后看 `.omc/state/last-tool-error.json`；备份在 `<library>/.skill-adopt-backup/` 或 `.backup_nested_migration/`。

## 错误处理

| 场景 | 处理 |
|------|------|
| `index.json` 缺失 | `skillctl scan --config scan-config.yaml` |
| 目标 skill 不存在 | 检查 `--path` 与 `scan-config.yaml` |
| dedup 误判 | 确认 `is_symlink()` 解析（junction 在 Windows 需 resolve）|
| 写操作半途失败 | 查看 `.omc/state/last-tool-error.json` + 备份目录回滚 |
| symlink 创建失败（Windows）| 启用 Developer Mode 或用 junction（默认）|

## 嵌套仓库

Git repo 内 `skills/` 子目录（如 `ljg-skills/skills/ljg-card`）是正常组织方式，**不算重复**，不做去重。`migrate` 命令可一次性迁到主库。

## 安全边界

- **不会**删除未确认的文件——所有写操作需 `--yes` 显式确认
- **不会**发送外部请求——纯本地操作，不联网
- **不会**修改 skill 内容——只管理位置（symlink/复制），不改 SKILL.md 正文
- **会**创建 symlink/junction——Windows 需 Developer Mode 或管理员权限
- **会**读取 scan-config.yaml 中列出的所有目录

## 详细文档

- [CLI 完整规范](references/cli-spec.md)
- [架构与状态](references/architecture.md)
- [用户配置 user.json](references/user-config.md)
- [scan-config 示例](references/scan-config.example.yaml)

运行 `skillctl <cmd> --help` 查看每个命令的完整参数清单。