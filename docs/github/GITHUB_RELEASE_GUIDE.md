# GitHub 发布指南

## 概述

本文档详细描述如何将项目发布到 GitHub，包含配置步骤、脚本使用方法和最佳实践。

## 目录

1. [前置准备](#前置准备)
2. [配置文件说明](#配置文件说明)
3. [发布脚本使用](#发布脚本使用)
4. [手动发布步骤](#手动发布步骤)
5. [安全注意事项](#安全注意事项)
6. [故障排除](#故障排除)

---

## 1. 前置准备

### 1.1 创建 GitHub 账号

如果你还没有 GitHub 账号，请先注册：
- 访问 [github.com](https://github.com)
- 完成注册流程

### 1.2 生成 Personal Access Token

1. 登录 GitHub → 点击右上角头像 → **Settings**
2. 左侧菜单底部 → **Developer settings**
3. **Personal access tokens** → **Tokens (classic)**
4. 点击 **Generate new token**
5. 设置以下内容：
   - **Note**: 描述用途（例如：pms-ai-selection 发布）
   - **Expiration**: 建议设置 90 天
   - **Scopes**: 勾选 `repo`（完整仓库控制）
6. 点击 **Generate token**
7. **复制生成的 token**（以 `ghp_` 开头），只显示一次！

---

## 2. 配置文件说明

### 2.1 配置文件位置

```
.github-publish.env
```

### 2.2 配置项说明

| 配置项 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `GITHUB_USERNAME` | ✅ | - | 你的 GitHub 用户名 |
| `GITHUB_TOKEN` | ✅ | - | Personal Access Token |
| `REPO_NAME` | ❌ | `pms-ai-selection` | 仓库名称 |
| `REPO_VISIBILITY` | ❌ | `public` | 仓库可见性（public/private） |
| `REPO_DESCRIPTION` | ❌ | - | 仓库描述 |
| `REPO_HOMEPAGE` | ❌ | - | 仓库主页 URL |

### 2.3 配置示例

```ini
# GitHub 账号信息
GITHUB_USERNAME=your-github-username
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 仓库配置
REPO_NAME=pms-ai-selection
REPO_VISIBILITY=public
REPO_DESCRIPTION="Enterprise-grade AI product selection decision hub"
REPO_HOMEPAGE=https://github.com/your-github-username/pms-ai-selection
```

---

## 3. 发布脚本使用

### 3.1 Windows (PowerShell)

```powershell
# 进入项目目录
cd d:\Project\fms

# 运行发布脚本
.\scripts\publish_to_github.ps1

# 跳过创建仓库（适用于已存在的仓库）
.\scripts\publish_to_github.ps1 -SkipCreateRepo
```

### 3.2 Linux/Mac (Shell)

```bash
# 进入项目目录
cd /path/to/fms

# 赋予执行权限
chmod +x scripts/publish_to_github.sh

# 运行发布脚本
./scripts/publish_to_github.sh
```

### 3.3 脚本功能

脚本会自动完成以下操作：

1. ✅ 读取配置文件
2. ✅ 检查并安装 GitHub CLI
3. ✅ 使用 Token 登录 GitHub
4. ✅ 创建远程仓库（如果不存在）
5. ✅ 配置 git 远程地址
6. ✅ 提交并推送代码
7. ✅ 显示发布结果

---

## 4. 手动发布步骤

如果你不想使用脚本，可以按照以下步骤手动发布：

### 4.1 添加远程仓库

```bash
# 设置变量
GITHUB_USERNAME="your-username"
GITHUB_TOKEN="ghp_xxx"
REPO_NAME="pms-ai-selection"

# 添加远程仓库
git remote add origin "https://$GITHUB_USERNAME:$GITHUB_TOKEN@github.com/$GITHUB_USERNAME/$REPO_NAME.git"

# 验证远程仓库配置
git remote -v
```

### 4.2 创建仓库（需要 gh CLI）

```bash
# 安装 gh CLI
# Windows: winget install GitHub.cli
# macOS: brew install gh
# Linux: 参考 https://github.com/cli/cli#installation

# 登录
echo "$GITHUB_TOKEN" | gh auth login --with-token

# 创建仓库
gh repo create "$REPO_NAME" --public --description "AI product selection system"
```

### 4.3 推送代码

```bash
# 提交代码
git add .
git commit -m "chore: initial commit - AI product selection system"

# 推送主分支
git branch -M main
git push -u origin main
```

---

## 5. 安全注意事项

### 5.1 Token 安全

- ✅ Token 只显示一次，请妥善保存
- ✅ 不要将 Token 提交到版本控制
- ✅ 设置合理的过期时间
- ✅ 只授予必要的权限（最小权限原则）

### 5.2 配置文件安全

- ✅ `.github-publish.env` 已添加到 `.gitignore`
- ✅ 不要在公共场合分享配置文件内容
- ✅ 定期轮换 Token

### 5.3 凭证管理

```bash
# 配置 git 缓存凭证（避免每次输入密码）
git config credential.helper cache  # 临时缓存（15分钟）
git config credential.helper 'cache --timeout=3600'  # 缓存1小时

# 永久存储（不推荐在公共机器上使用）
# Windows: git config credential.helper wincred
# Linux/Mac: git config credential.helper store
```

---

## 6. 故障排除

### 6.1 常见错误

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `GITHUB_USERNAME 未配置` | 配置文件缺失或未填写 | 检查 `.github-publish.env` 文件 |
| `GITHUB_TOKEN 未配置` | Token 缺失 | 重新生成 Token 并填写 |
| `gh 无法识别` | GitHub CLI 未安装 | 运行脚本自动安装或手动安装 |
| `Repository already exists` | 仓库已存在 | 使用 `-SkipCreateRepo` 参数 |
| `Permission denied` | Token 权限不足 | 确保勾选了 `repo` 权限 |
| `remote: Repository not found` | 仓库不存在且未创建 | 确保运行脚本创建仓库 |

### 6.2 验证发布

发布成功后，验证步骤：

1. 访问 `https://github.com/你的用户名/pms-ai-selection`
2. 确认代码已推送
3. 确认 README.md 正确显示
4. 检查仓库设置是否正确

---

## 附录

### A. GitHub CLI 安装参考

- **Windows**: `winget install GitHub.cli`
- **macOS**: `brew install gh`
- **Linux**: 参考 [官方文档](https://github.com/cli/cli#installation)

### B. 相关文件

| 文件 | 说明 |
|------|------|
| `.github-publish.env` | 发布配置文件 |
| `scripts/publish_to_github.ps1` | Windows 发布脚本 |
| `scripts/publish_to_github.sh` | Linux/Mac 发布脚本 |
| `.gitignore` | Git 忽略配置（已包含敏感文件） |

### C. 发布流程图

```
┌─────────────────────────────────────────────────────────┐
│                   发布流程                              │
├─────────────────────────────────────────────────────────┤
│  1. 准备阶段                                           │
│     ├─ 注册 GitHub 账号                                │
│     └─ 生成 Personal Access Token                      │
│                                                        │
│  2. 配置阶段                                           │
│     └─ 填写 .github-publish.env                        │
│                                                        │
│  3. 执行阶段                                           │
│     ├─ 运行发布脚本                                    │
│     ├─ 创建远程仓库                                    │
│     ├─ 配置 git remote                                │
│     └─ 推送代码                                        │
│                                                        │
│  4. 验证阶段                                           │
│     └─ 在浏览器中确认仓库                               │
└─────────────────────────────────────────────────────────┘
```