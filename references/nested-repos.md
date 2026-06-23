# 嵌套仓库处理

## 什么是嵌套仓库

嵌套仓库是指 Git repo 内包�?`skills/` 子目录的结构�?
```
ljg-skills/                    # Git repo（根目录�?.git�?├── .git/
├── SKILL.md                   # Repo 自身�?skill 入口
├── skills/                    # 嵌套�?skills 目录
�?  ├── ljg-card/
�?  �?  └── SKILL.md
�?  ├── ljg-paper/
�?  �?  └── SKILL.md
�?  └── ...
└── scripts/
```

## 常见嵌套仓库

| Repo | 嵌套路径 | 说明 |
|------|---------|------|
| ljg-skills | skills/*/SKILL.md | 李继刚个人技能包 |
| minimax-skills | skills/*/SKILL.md | MiniMax AI 技能包 |
| money-skills | skills/*/SKILL.md | 生意赚钱技能包 |
| baoyu-skills | skills/*/SKILL.md | 宝俞系列工具�?|
| Waza | skills/*/SKILL.md | Waza 技能集�?|
| yao-open-skills | skills/*/SKILL.md | Yao 开放技能库 |

## 自动检�?
`scan_and_index.py` 会自动检测嵌套仓库：

```python
# 检测逻辑
for repo in scan_path.iterdir():
    if (repo / ".git").exists() and (repo / "skills").is_dir():
        # 发现嵌套仓库
        nested_repos.append({
            "repo_path": str(repo),
            "skills_path": str(repo / "skills"),
            "git_url": get_remote_url(repo)
        })
```

## 这算重复吗？

**不算�?* 嵌套�?Git repo 里的 skills 是正常的组织方式�?
1. **版本同步**：所有嵌�?skills 跟随 repo 统一版本管理
2. **原子更新**：一�?git pull 更新所有嵌�?skills
3. **独立访问**：每�?nested skill 可以独立被引�?
```
# resolve 后都指向同一个物理位�?<library>\ljg-skills\skills\ljg-card    # 真实位置
~/.claude\skills\ljg-skills\skills\ljg-card  # symlink �?同一位置
```

## 扫描行为

�?`auto_detect_nested=true` 时：

1. 发现 `xxx/.git` + `xxx/skills/` 结构
2. 将嵌套路径添加到扫描列表
3. index.json 中记�?`nested_repos` 字段

```json
{
  "nested_repos": [
    {
      "repo_path": "<library_path>/<wrapper_repo>",
      "skills_path": "<library_path>/<wrapper_repo>/skills",
      "git_url": "https://github.com/<owner>/<wrapper_repo>.git"
    }
  ]
}
```

## 不需要做什�?
- **不要**把嵌�?skills 挪到外层
- **不要**担心"这么多层会不会有问题"
- **不要**尝试把它们合并成一个扁平结�?
嵌套�?GitHub 推崇�?repos 风格（如 github.com/org/repo-name），保持原样即可�?