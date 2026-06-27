# 常见场景 Recipe (v3.0)

## Recipe 1: 首次接入

**场景**：新机器 / �?library，需要从零开始�?
```bash
# 1. 初始�?CLI 状态目�?skillctl init

# 2. 编辑 scan-config.yaml，配置扫描路�?#    （首次可能要复制 scan-config.example.yaml�?
# 3. 扫描构建索引
skillctl scan --config scan-config.yaml

# 4. 看一眼库状�?skillctl list --json | head
skillctl status
```

## Recipe 2: 接入�?skill

**场景**：`~/.claude/skills/` 下有人手动放�?`my-new-skill/`，要纳入管理�?
```bash
# 1. 预览要采纳的 skill
skillctl adopt --dry-run

# 2. 确认无误后执行（带备份）
#    v5+: gate 验证（validate + score）先通过才执行；--non-interactive 自动确认通过后的 prompt
skillctl adopt --yes --non-interactive

# 3. 验证：index.json 已更新，原位置变 junction
skillctl status
```

## Recipe 3: 在多个项目共�?skill

**场景**：`<library>\skillctl` 是主库，要在项目 A �?`.claude/skills/` 链接 `ljg-card` + `x-tweet-fetcher`�?
```bash
# 1. 预览链接动作
skillctl link --target ~/projects/projectA/.claude/skills \
              --skills ljg-card,x-tweet-fetcher --dry-run

# 2. 确认后执�?skillctl link --target ~/projects/projectA/.claude/skills \
              --skills ljg-card,x-tweet-fetcher --yes
```

## Recipe 4: 检测并去重

**场景**：怀疑库里有重复 skill（同一份内容在两个物理位置）�?
```bash
# 1. 重建索引（确保最新）
skillctl scan --config scan-config.yaml

# 2. 分析重复
skillctl dedup --analyze

# 3. 选择策略
#    --strategy global   自动保留 global，移�?local
#    --strategy local    反之
#    --interactive       每条询问
skillctl dedup --strategy global --yes
```

**注意**：嵌套仓库（Git repo �?`skills/`）不算重复，会被 dedup 自动跳过�?
## Recipe 0: �?GitHub 安装 skill 仓库（保留父目录 + git 历史�?
**场景**：想把一�?GitHub 仓库（可能含 N �?skill）整库装到本地，**保留父目录的 `.git/`** 以便后续 `git pull` 更新，而不是把 N �?skill 拍平到顶层�?
```bash
# 1. 装一个含�?skill 的仓库（典型场景：skill 集合 repo�?skillctl install --non-interactive https://github.com/user/my-multi-skill-repo

# 装完后：
#   <library>\my-multi-skill-repo\.git\         �?父目录有完整 git 历史
#   <library>\my-multi-skill-repo\skill-1\      �?原仓库结构保�?#   <library>\my-multi-skill-repo\skill-2\
#   ...

# 2. 把装好的�?skill 收进 index.json
skillctl scan

# 3. 之后更新——一键刷所�?wrapper repo
skillctl update --repos            # 默认 live pull
skillctl update --repos --dry-run  # 预览
```

**冲突处理**：如�?`library/<repo-name>/` 已存在且非空�?
```bash
# 默认拒绝（保护现有内容）
skillctl install --non-interactive https://github.com/user/repo
# �?Install failed: Path exists and is not empty: .../repo.
#   Use --reinstall to overwrite (backs up to .skillctl-backup/).

# 明确想覆盖时�?skillctl install --reinstall --non-interactive https://github.com/user/repo
# �?Installed to: .../repo
#   Previous content backed up to: .../lib/.skillctl-backup/repo_<ts>/
```

注意备份**只含工作�?*（不�?`.git/`）——`.git/` �?remote 可重新拉取，且包�?Windows 文件锁的 pack 文件，硬备份会失败�?
## Recipe 5: 接收 Git 远程更新

**场景**：某�?skill 来自 Git 仓库，要拉取最新。两条路径：

```bash
# 路径 A: per-skill（基�?index.json，传统方式）
skillctl update --json              # 看哪些有更新
skillctl update --fetch             # �?fetch 再判断（更准但慢�?skillctl update --skill ljg-card --json  # 单个 skill 详细

# 路径 B: 批量 wrapper-repo（v3.1+，扫文件系统，不依赖 index�?skillctl update --repos --dry-run   # 看哪�?wrapper / per-skill .git 会被 pull
skillctl update --repos             # live pull（默认）
skillctl update --repos --timeout 120 --library E:/my-lib  # 自定义超�?+ 库路�?```

`update --repos` 一次扫所有直�?`<library>/<name>/.git/` 子目录（�?wrapper 仓库 + �?skill 自带 `.git`），逐个 `git fetch && git pull --ff-only`。一�?repo 出错不影响其他，结果汇总报告（Pulled / Skipped / Errors）�?
## Recipe 6: 治理验证（CI 用）

**场景**：CI 阶段检查所�?skill 是否合规�?
```bash
skillctl validate --strict --json | \
  python -c "import sys, json; d=json.load(sys.stdin); sys.exit(0 if d.get('all_valid') else 1)"
```

## Recipe 7: 清理孤立 symlink

**场景**：library 里有 symlink 指向不存在的目标�?
```bash
# 1. 预览
skillctl cleanup --dry-run --scan-path <library>

# 2. 实际清理
skillctl cleanup --remove --scan-path <library>
```

## Recipe 8: 嵌套仓库迁移到主�?
**场景**：`ljg-skills/skills/ljg-card` 嵌套仓库，要扁平化到主库�?
```bash
# 1. 预览（不实际执行�?skillctl migrate --dry-run --non-interactive

# 2. 执行
skillctl migrate --execute --non-interactive
```

迁移后：
- 物理文件�?`ljg-skills/skills/ljg-card/` 复制�?`<library>\ljg-card/`
- 嵌套 repo 保留（仍�?`git pull` 更新�?- 自动重建 index

## Recipe 9: 删除 skill（不可逆 — 不再自动备份）

**v6 设计变更**：`delete` 不再创建备份。删除是不可逆的，要保留请先自己 `cp -r`。

```bash
# 1. 默认行为：3 秒倒计时，Ctrl-C 中止
skillctl delete old-skill

# 2. CI / 脚本模式：跳过倒计时
skillctl delete old-skill --yes

# 3. 后悔了？重新装回来
#    如果 index.json 里记录了 GitHub URL，CLI 会自动提示：
#      "To restore: skillctl install <github_url>"
#    否则手动恢复。
```

**为什么这样**：v6 之前每个写命令各自定义备份目录（`.delete-backup` / `.skill-adopt-backup` / `.backup_nested_migration` / `.skillctl-backup`），用户心智负担重、备份无限累积。现在统一到 `<library>/.skillctl-backup/<date>/<op>-<target>_<ts>/`，**成功即删**，**失败才留**。删除单独走 3 秒倒计时 + post-delete notice 提示 GitHub URL，不混进备份机制。

## Recipe 10: 批量操作（loop�?
**场景**：要给所�?skill 跑治理验证�?
```bash
# 列出所�?skill �?skillctl list --json | python -c "
import sys, json
data = json.load(sys.stdin)
for s in data.get('skills', []):
    print(s)
" | while read skill; do
    echo "=== $skill ==="
    skillctl validate --skill "$skill" --json
done
```

## Recipe 11: 出错恢复

**场景**：写操作中途失败，index / 磁盘状态不一致。

**v6 变更**：所有失败留下的备份都在同一个目录树，按日期分桶。

```bash
# 1. 看最近错误
skillctl status        # 读 last-tool-error.json
cat .omc/state/last-tool-error.json

# 2. 找失败的备份（v6 之前还要去 3 个不同目录找）
ls -la <library>/.skillctl-backup/<YYYY-MM-DD>/
# 例：.skillctl-backup/2026-06-27/migrate-my-skills_143022/

# 3. 重建索引（最常见的恢复手段）
skillctl scan --config scan-config.yaml

# 4. 物理回滚（如果上一步没用）
cp -r <library>/.skillctl-backup/<date>/<op>-<target>_<ts>/<skill-name>/ <library>/
skillctl scan --config scan-config.yaml
```

**成功的写操作不会留任何备份**（v6 起 auto-commit）。只有失败才有备份可恢复。
## Recipe 12: Dry-run 优先（写操作铁律�?
**所有写操作前先 dry-run**�?
```bash
# 错误
skillctl adopt --yes

# 正确
skillctl adopt --dry-run
# 看清楚输�?skillctl adopt --yes --non-interactive --backup .skill-adopt-backup  # v5+: gate 先验证
```

写操作铁律：dry-run �?人工确认 �?--yes --backup 三步走�?
## Recipe 13: install 出错后恢�?
**场景**：`skillctl install` 失败后想恢复现场�?
```bash
# 1. 看错误信�?skillctl status
cat .omc/state/last-tool-error.json

# 2. �?install 备份
ls -la <library>/.skillctl-backup/    # install 的备份目�?
# 3. 恢复工作树（备份不含 .git/，从 remote 重新拉）
cp -r <library>/.skillctl-backup/<repo>_<ts>/* <library>/<repo>/
# 然后单独恢复 .git/：从 remote 重新 clone �?git init + git remote add + git fetch

# 4. 重建索引
skillctl scan --config scan-config.yaml
```

**典型失败模式**

| 错误 | 原因 | 恢复 |
|------|------|------|
| `Path exists and is not empty` | 目标 wrapper 已存�?| �?`--reinstall`，或�?URL / 手动改名 |
| `Backup failed: [WinError 5]` | Windows 文件锁（旧版会失败，v3.1+ 已绕过） | 重试；如持续失败，手�?`mv <library>/<repo> <library>/<repo>.bak` �?install |
| `Clone timed out` | 网络/远端�?| 重试；或�?`--depth 1`（已是默认） |
