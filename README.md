# ace-assistant

可复用的 AI CI 工作流（GitHub Actions）。提供 AI 驱动的 Issue 分诊、自动代码修复和 PR 审查，作为集中式可复用工作流供任意仓库接入。

## 功能特性

- **AI 调度（Dispatch）** — 监听 Issue、评论和 PR 事件，通过 AI 进行分诊，路由至修复或审查
- **AI 修复（Fix）** — 自动创建分支，使用 AI 生成修复代码，提交并创建 PR
- **AI 审查（Review）** — AI 审查 PR，批准或提出修改建议，支持自动循环（审查 → 修复 → 再审查）
- `.github/opencode.json` 和 `.opencode/oh-my-openagent.json` 是对外及对内共享的配置文件，用于配置 AI 代理的模型和参数，避免在每个仓库中重复配置

## 快速开始

### 1. 复制 Caller Workflow

将 `templates/` 目录下的 3 个 caller workflow 模板复制到你的业务仓库的 `.github/workflows/`：

```bash
# 在你的业务仓库根目录执行
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/dispatch.yml \
  -o .github/workflows/dispatch.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/fix.yml \
  -o .github/workflows/fix.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/review.yml \
  -o .github/workflows/review.yml
```

### 2. 替换占位符

将 3 个 workflow 文件中的 `ORG/ace-assistant` 替换为实际的组织/仓库路径：

```bash
sed -i 's|ORG/ace-assistant|your-org/ace-assistant|g' \
  .github/workflows/dispatch.yml \
  .github/workflows/fix.yml \
  .github/workflows/review.yml
```

### 3. 添加配置文件

在你的仓库中创建 `.github/ace-config.json`。完整示例见 `templates/config.example.json`。

需要自定义的关键字段：

| 字段 | 说明 |
|------|------|
| `tech_stack.language` | 项目主要编程语言 |
| `tech_stack.package_manager` | 包管理器（npm、uv、cargo 等） |
| `tech_stack.test_command` | 运行测试的命令 |
| `tech_stack.type_check_command` | 类型检查命令（可选） |
| `bot.name` | AI 提交时的 Git 作者名称 |
| `bot.email` | AI 提交时的 Git 作者邮箱 |
| `branch.prefix` | AI 创建分支的命名前缀 |
| `chatops.command_prefix` | ChatOps 命令前缀（默认：`ace`） |

### 4. 配置 Secrets

在你的仓库中添加以下 Secrets（Settings → Secrets and variables → Actions）：

| Secret | 说明 | 是否必需 |
|--------|------|----------|
| `OPENCODE_AUTH_JSON_B64` | Base64 编码的 OpenCode 认证 JSON | 是 |
| `GH_PAT` | 具有 `repo` + `workflow` 权限的 GitHub Personal Access Token | 是 |

PAT 需要 `repo` 和 `workflow` 权限，用于调度工作流和管理 PR/Issue。

### 5.（可选）添加 Issue 模板

创建 `.github/ISSUE_TEMPLATE/bug-report.yml`，包含以下表单字段供 AI 解析：

- **标题** — Bug 的简短描述
- **描述** — 详细的复现步骤
- **基准分支** — 创建修复的源分支（默认：`main`）

## 架构

```
业务仓库                                ace-assistant 仓库
┌─────────────────┐                   ┌──────────────────────┐
│ .github/        │                   │ .github/             │
│   workflows/    │    workflow_call  │   workflows/         │
│     dispatch    ├──────────────────►│     reusable-dispatch.yml  │
│     fix         ├──────────────────►│     reusable-fix.yml       │
│     review      ├──────────────────►│     reusable-review.yml    │
│   ace-config.json                   │   actions/           │
│                 │                   │     ace-worker-bootstrap/
└─────────────────┘                   │     setup-opencode/  │
                                      │     configure-git/   │
                                      │     ...              │
                                      │ scripts/ci/          │
                                      └──────────────────────┘
```

**Caller Workflow**（在你的仓库中）是薄层包装器：监听事件、传递输入给可复用工作流，并根据输出进行路由。

**Reusable Workflow**（在本仓库中）包含所有 AI 逻辑、Composite Action 和 Python 脚本。

## 工作流详情

### reusable-dispatch（可复用工作流）

接收序列化的事件数据并执行：
- **Issue 分诊**：AI 分析 Issue，分类并路由至修复
- **ChatOps**：解析评论中的 `/ace fix`、`/ace review` 命令
- **PR 调度**：将 PR 事件路由至审查工作流
- **手动调度**：通过 `workflow_dispatch` 直接路由

**输出**：`route_to`（`fix` | `review` | `none`）和 `route_params`（JSON）

### reusable-fix（可复用工作流）

执行 AI 驱动的代码修复：
1. 解析 Issue/PR 上下文
2. 创建工作分支
3. 运行 OpenCode AI Agent 生成修复代码
4. 提交变更并创建/更新 PR
5. 可选：修复完成后自动触发审查

### reusable-review（可复用工作流）

执行 AI 驱动的 PR 审查：
1. 获取 PR 的 diff 和上下文信息
2. 运行 OpenCode AI Agent 进行审查
3. 提交审查结果（批准 / 请求修改 / 评论）
4. 支持多轮审查循环

**输出**：`needs_fix` 和 `fix_params`，用于自动循环

## 所需权限

Caller Workflow 必须声明以下权限：

| 工作流 | 权限 |
|--------|------|
| dispatch | `contents: read`、`issues: write`、`pull-requests: write`、`actions: write` |
| fix | `contents: write`、`issues: write`、`pull-requests: write`、`actions: write` |
| review | `contents: read`、`issues: write`、`pull-requests: write`、`actions: write` |

## 版本固定

Caller Workflow 应固定到主版本 tag：

```yaml
uses: your-org/ace-assistant/.github/workflows/reusable-fix.yml@v1
```

这样 ace-assistant 的非破坏性更新（Bug 修复、功能改进）会自动生效，无需修改 Caller Workflow。

### `v1` 的含义

`v1` 是维护者手动维护的主版本 tag，不是 GitHub Actions 自动生成的概念。

发布流程：

```bash
# 1) 先创建不可变的具体版本 tag
git tag -a v1.0.0 -m "Release v1.0.0"

# 2) 再移动主版本别名 v1 到该版本
git tag -fa v1 -m "Move v1 to v1.0.0"

# 3) 推送到远端
git push origin v1.0.0
git push origin v1 --force
```

- 使用 `@v1` 的调用方，应预期接收兼容的 `1.x` 更新。
- 如果调用方需要更严格的变更控制，可以固定到具体 release tag 或 commit SHA。
- 仓库维护者应让 `v1` 始终指向最新稳定的 `1.x` 版本。

## 目录结构

```
.github/
  workflows/         # 可复用工作流（workflow_call）
    reusable-dispatch.yml  # Issue 分诊 + 事件路由
    reusable-fix.yml       # AI 代码修复
    reusable-review.yml    # AI PR 审查
  actions/           # Composite Actions
    ace-worker-bootstrap/  # 双重 checkout + 环境搭建
    setup-opencode/       # OpenCode 认证配置
    configure-git/        # Git 身份配置
    git-commit-push/      # 提交并推送变更
    load-error-config/    # 加载错误恢复配置
    ensure-labels/        # 确保标签存在
    upsert-marker-comment/ # 创建/更新标记评论
    check-failure-count/  # 连续失败次数守卫
scripts/
  ci/                # Python CI 脚本（仅依赖标准库）
templates/           # Caller Workflow 模板
  dispatch.yml
  fix.yml
  review.yml
  config.example.json
tests/
  ci/                # CI 脚本测试套件
```

## 开发指南

### 前置要求

- Python 3.12+

### 运行测试

```bash
pip install pytest pyyaml
PYTHONPATH=. python -m pytest tests/ -v
```

### 脚本使用

CI 脚本以模块方式调用：

```bash
python -m scripts.ci.build_prompt --help
python -m scripts.ci.parse_issue_form --help
```
