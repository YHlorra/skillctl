# Governance Validation Standard

本文档定义 skillctl 的治理验证标准，用于确保 Skill 包的质量和安全性。

## 验证目标

1. **结构完整性** - SKILL.md 格式正确，必填字段存在
2. **安全性** - 无敏感信息泄露（API keys, tokens, passwords）
3. **代码质量** - 无危险模式（eval, shell injection 等）

---

## 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | Skill 名称（唯一标识） |
| `description` | string | 功能描述（20-300 字符） |

## 推荐字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 版本号 |
| `scope` | string | global 或 project |
| `source_type` | string | github / local / derived |
| `github_url` | string | GitHub 仓库地址 |
| `github_hash` | string | 当前 commit hash |

---

## 安全扫描模式

### 高风险（EXTREME/HIGH）

| 模式 | 说明 |
|------|------|
| `ghp_[a-zA-Z0-9]{36}` | GitHub Personal Access Token |
| `sk-[a-zA-Z0-9]{48}` | OpenAI API Key |
| `AKIA[a-zA-Z0-9]{16}` | AWS Access Key |
| `api_key\s*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]` | 通用 API Key |
| `secret_key\s*[=:]\s*['\"][a-zA-Z0-9]{20,}['\"]` | 通用 Secret Key |
| `password\s*[=:]\s*['\"][^'\"]{8,}['\"]` | 明文密码 |
| `token\s*[=:]\s*['\"][a-zA-Z0-9_-]{20,}['\"]` | 通用 Token |
| `base64\.(decode\|b64decode)\s*\(` | Base64 解码（可能混淆） |
| `__import__\s*\(['\"]` | 动态导入 |
| `MEMORY\.md\|USER\.md\|SOUL\.md\|IDENTITY\.md` | 访问 agent 记忆/身份文件 |

### 网络安全（MEDIUM）

| 模式 | 说明 |
|------|------|
| `curl\s+['\"]https?://[^'\"]+['\"]\s+(-o\|--output)` | curl 下载到未知 URL |
| `wget\s+['\"]https?://[^'\"]+['\"]` | wget 未知 URL |
| `requests\.get\s*\(['\"]http://` | HTTP（非 HTTPS）请求 |
| `urllib\.request\.urlopen\s*\(['\"]http://` | urllib HTTP 请求 |

### 代码风险（ERROR 级别）

| 模式 | 说明 |
|------|------|
| `eval\s*\(` | eval() 使用 - 代码注入风险 |
| `exec\s*\(` | exec() 使用 - 代码注入风险 |
| `subprocess\.call\s*\([^)]*shell\s*=\s*True` | shell=True - 命令注入风险 |

### 代码问题（WARNING/INFO）

| 模式 | 级别 | 说明 |
|------|------|------|
| `TODO(?!\w)` | warning | 未处理的 TODO |
| `FIXME(?!\w)` | warning | 未修复的 FIXME |
| `console\.(log\|debug\|info)\s*\(` | info | 调试 console 语句 |
| `print\s*\(` | info | Print 语句（应用 logging） |
| `os\.system\s*\(` | warning | os.system() 调用 |

---

## 风险等级分类

| 等级 | 条件 | 处理 |
|------|------|------|
| **EXTREME** | 发现 GitHub PAT、AWS Key 等高危凭证 | 必须修复 |
| **HIGH** | 发现 API Key、Password、动态导入等 | 必须修复 |
| **MEDIUM** | 发现 HTTP 请求、Socket 等 | 建议修复 |
| **LOW** | 只有 info/warning 级别问题 | 可选修复 |
| **PASS** | 无问题 | 通过 |

---

## 验证流程

```bash
# 验证所有 skills
python scripts/governance_validate.py --path ../skillctl

# 验证单个 skill
python scripts/governance_validate.py --skill skill-name

# JSON 输出
python scripts/governance_validate.py --json

# 自动修复（部分问题）
python scripts/governance_validate.py --fix
```

## 输出格式

```
=== Governance Validation Results ===

Skill: example-skill
  Score: 85/100
  Risk Level: MEDIUM
  Issues:
    [warning] security: curl to unknown URL detected
    [info] code: print statement found

Summary:
  Total: 10 skills checked
  EXTREME: 0
  HIGH: 0
  MEDIUM: 2
  LOW: 5
  PASS: 3
```

---

## 修复建议

1. **凭证清理** - 移除硬编码的 API keys/tokens，使用环境变量
2. **HTTPS** - 将 HTTP 请求改为 HTTPS
3. **避免 eval/exec** - 使用安全的替代方案
4. **移除调试代码** - 删除 console.log, print 等调试语句

---

## 相关文档

- [架构设计](architecture.md)
- [嵌套仓库处理](nested-repos.md)