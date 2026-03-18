#!/bin/bash
#
# 发布新的 ace-assistant 版本 tag
# 使用方式: ./scripts/publish-tag.sh [version|bump]
#
# 参数:
#   version: 指定版本号，如 1.0.10、1.1.0
#   bump:    自动递增 patch 版本 (v1.0.9 -> v1.0.10)
#
# 示例:
#   ./scripts/publish-tag.sh 1.0.10     # 发布 v1.0.10
#   ./scripts/publish-tag.sh bump       # 自动递增 patch
#

set -e

# 获取最新 tag
get_latest_tag() {
    git tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1
}

# 解析版本号 (v1.0.10 -> 1 0 10)
parse_version() {
    local version="$1"
    version="${version#v}"  # 去掉 v 前缀
    echo "$version"
}

# 递增 patch 版本
bump_patch() {
    local latest="$1"
    latest="${latest#v}"
    local major minor patch
    IFS='.' read -r major minor patch <<< "$latest"
    patch=$((patch + 1))
    echo "${major}.${minor}.${patch}"
}

# 验证版本号格式
validate_version() {
    local version="$1"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "错误: 版本号格式无效 '$version'，应为 X.Y.Z 格式（如 1.0.10）"
        exit 1
    fi
}

# 检查是否在 main 分支
check_branch() {
    local current_branch
    current_branch=$(git branch --show-current)
    if [[ "$current_branch" != "main" ]]; then
        echo "警告: 当前分支是 '$current_branch'，不是 'main'"
        read -p "是否继续? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "已取消"
            exit 1
        fi
    fi
}

# 检查工作区是否干净
check_clean() {
    if [[ -n $(git status --porcelain) ]]; then
        echo "错误: 工作区有未提交的更改，请先提交或暂存"
        git status --short
        exit 1
    fi
}

# 主逻辑
main() {
    local input="${1:-bump}"
    local new_version
    local latest_tag

    # 获取最新 tag
    latest_tag=$(get_latest_tag)
    if [[ -z "$latest_tag" ]]; then
        echo "错误: 未找到现有版本 tag"
        exit 1
    fi

    echo "当前最新版本: $latest_tag"

    # 确定新版本
    if [[ "$input" == "bump" ]]; then
        new_version=$(bump_patch "$latest_tag")
        echo "将发布新版本: v${new_version}"
    else
        new_version="$input"
        validate_version "$new_version"
        new_version=$(parse_version "$new_version")
        if [[ "v${new_version}" == "$latest_tag" ]]; then
            echo "错误: 版本 v${new_version} 已存在"
            exit 1
        fi
        echo "将发布指定版本: v${new_version}"
    fi

    # 检查分支和工作区
    check_branch
    check_clean

    # 确认
    local major_version
    major_version=$(echo "$new_version" | cut -d. -f1)
    echo ""
    echo "发布详情:"
    echo "  具体版本: v${new_version}"
    echo "  主版本别名: v${major_version} (将移动到 v${new_version})"
    echo ""
    read -p "确认发布? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 1
    fi

    # 执行发布
    echo ""
    echo "正在创建 tag..."

    # 1) 创建具体版本 tag
    git tag -a "v${new_version}" -m "Release v${new_version}"
    echo "✓ 创建 tag: v${new_version}"

    # 2) 移动主版本别名
    git tag -fa "v${major_version}" -m "Move v${major_version} to v${new_version}"
    echo "✓ 移动主版本别名: v${major_version} -> v${new_version}"

    # 3) 推送到远端
    echo ""
    echo "正在推送到远端..."
    git push origin "v${new_version}"
    git push origin "v${major_version}" --force

    echo ""
    echo "✅ 发布成功!"
    echo ""
    echo "用户现在可以通过以下方式引用:"
    echo "  uses: your-org/ace-assistant/.github/workflows/ace-fix.yml@v${major_version}"
    echo "  或固定到具体版本:"
    echo "  uses: your-org/ace-assistant/.github/workflows/ace-fix.yml@v${new_version}"
}

# 显示帮助
show_help() {
    cat << 'EOF'
发布 ace-assistant 版本 tag

用法: ./scripts/publish-tag.sh [version|bump]

参数:
  version    指定版本号，如 1.0.10、1.1.0、2.0.0
  bump       自动递增 patch 版本 (默认)

示例:
  ./scripts/publish-tag.sh bump       # v1.0.9 -> v1.0.10
  ./scripts/publish-tag.sh 1.0.10     # 发布 v1.0.10
  ./scripts/publish-tag.sh 1.1.0      # 发布 v1.1.0 (minor 更新)

发布流程:
  1. 检查当前分支和工作区状态
  2. 创建具体版本 tag (如 v1.0.10)
  3. 移动主版本 alias (如 v1 -> v1.0.10)
  4. 推送到远端

EOF
}

# 处理帮助参数
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

main "$@"
