#!/bin/bash
# ==============================================================================
# GitHub 发布脚本 (Linux/Mac)
# ==============================================================================
# 用途：自动化发布项目到 GitHub 仓库
# 依赖：gh CLI, git
# 配置文件：.github-publish.env
# ==============================================================================

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

function print_color() {
    echo -e "$1$2${NC}"
}

function read_config() {
    local path="$1"
    
    if [ ! -f "$path" ]; then
        print_color "$RED" "错误: 配置文件 $path 不存在!"
        exit 1
    fi
    
    # 读取配置到环境变量
    while IFS='=' read -r key value; do
        key=$(echo "$key" | tr -d ' ')
        value=$(echo "$value" | tr -d ' ')
        if [[ -n "$key" && ! "$key" =~ ^# && -n "$value" ]]; then
            export "$key=$value"
        fi
    done < "$path"
}

function test_gh_cli() {
    if command -v gh &> /dev/null; then
        return 0
    else
        return 1
    fi
}

function install_gh_cli() {
    print_color "$YELLOW" "正在安装 GitHub CLI..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        brew install gh
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        (type -p wget >/dev/null || (sudo apt update && sudo apt-get install wget -y)) \
        && sudo mkdir -p -m 755 /etc/apt/keyrings \
        && wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
        && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
        && sudo apt update \
        && sudo apt install gh -y
    else
        print_color "$RED" "不支持的操作系统，请手动安装 gh CLI"
        exit 1
    fi
}

function main() {
    print_color "$GREEN" "=============================================="
    print_color "$GREEN" "      GitHub 发布脚本 v1.0"
    print_color "$GREEN" "=============================================="
    echo ""

    # 1. 读取配置
    print_color "$YELLOW" "[1/5] 读取配置文件..."
    read_config ".github-publish.env"
    
    # 验证配置
    if [[ -z "$GITHUB_USERNAME" || "$GITHUB_USERNAME" == *"CHANGE_ME"* ]]; then
        print_color "$RED" "错误: GITHUB_USERNAME 未配置!"
        exit 1
    fi
    if [[ -z "$GITHUB_TOKEN" || "$GITHUB_TOKEN" == *"CHANGE_ME"* ]]; then
        print_color "$RED" "错误: GITHUB_TOKEN 未配置!"
        exit 1
    fi
    
    print_color "$GREEN" "  ✓ 用户名: $GITHUB_USERNAME"
    print_color "$GREEN" "  ✓ 仓库名: ${REPO_NAME:-pms-ai-selection}"
    print_color "$GREEN" "  ✓ 可见性: ${REPO_VISIBILITY:-public}"
    echo ""

    # 2. 检查 gh CLI
    print_color "$YELLOW" "[2/5] 检查 GitHub CLI..."
    if ! test_gh_cli; then
        print_color "$YELLOW" "  GitHub CLI 未安装，开始安装..."
        install_gh_cli
    else
        print_color "$GREEN" "  ✓ GitHub CLI 已安装"
    fi
    echo ""

    # 3. 登录 GitHub
    print_color "$YELLOW" "[3/5] 登录 GitHub..."
    export GH_TOKEN="$GITHUB_TOKEN"
    
    if ! gh auth status --with-token &>/dev/null; then
        print_color "$YELLOW" "  使用 token 登录..."
        echo "$GITHUB_TOKEN" | gh auth login --with-token
    fi
    print_color "$GREEN" "  ✓ 登录成功"
    echo ""

    # 4. 创建仓库
    print_color "$YELLOW" "[4/5] 创建 GitHub 仓库..."
    REPO_NAME="${REPO_NAME:-pms-ai-selection}"
    REPO_VISIBILITY="${REPO_VISIBILITY:-public}"
    
    if gh repo view "$GITHUB_USERNAME/$REPO_NAME" &>/dev/null; then
        print_color "$YELLOW" "  仓库已存在，跳过创建"
    else
        print_color "$YELLOW" "  创建仓库 $REPO_NAME..."
        gh repo create "$REPO_NAME" --$REPO_VISIBILITY --description "Enterprise-grade AI product selection decision hub" --homepage "https://github.com/$GITHUB_USERNAME/$REPO_NAME"
        print_color "$GREEN" "  ✓ 仓库创建成功"
    fi
    echo ""

    # 5. 推送代码
    print_color "$YELLOW" "[5/5] 推送代码到 GitHub..."
    
    # 配置远程仓库
    REMOTE_URL="https://$GITHUB_USERNAME:$GITHUB_TOKEN@github.com/$GITHUB_USERNAME/$REPO_NAME.git"
    git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
    
    print_color "$GREEN" "  ✓ 配置远程仓库"
    
    # 提交代码
    git add .
    git commit -m "chore: initial commit - AI product selection system" 2>/dev/null || true
    
    # 推送
    git branch -M main
    git push -u origin main
    
    print_color "$GREEN" "  ✓ 代码推送成功"
    echo ""

    # 完成
    print_color "$GREEN" "=============================================="
    print_color "$GREEN" "         发布完成!"
    print_color "$GREEN" "=============================================="
    echo ""
    print_color "$GREEN" "仓库地址: https://github.com/$GITHUB_USERNAME/$REPO_NAME"
    print_color "$YELLOW" "请在浏览器中访问确认"
}

# 执行主函数
main