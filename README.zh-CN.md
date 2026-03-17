# ace-assistant

可复用的 AI CI 工作流（GitHub Actions）。提供 AI 驱动的 Issue 分诊、自动代码修复和 PR 审查，作为集中式可复用工作流供任意仓库接入。

## 功能特性

- **AI 调度（Dispatch）** — 监听 Issue、评论和 PR 事件，通过 AI 进行分诊，路由至修复或审查
- **AI 修复（Fix）** — 自动创建分支，使用 AI 生成修复代码，提交并创建 PR
- **AI 审查（Review）** — AI 审查 PR，批准或提出修改建议，支持自动循环（审查 → 修复 → 再审查）

## 快速开始

### 1. 复制 Caller Workflow

将 `templates/` 目录下的 3 个 caller workflow 模板复制到你的业务仓库的 `.github/workflows/`：

```bash
# 在你的业务仓库根目录执行
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-dispatch.yml \
  -o .github/workflows/ace-dispatch.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-fix.yml \
  -o .github/workflows/ace-fix.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-review.yml \
  -o .github/workflows/ace-review.yml
```

### 2. 替换占位符

将 3 个 workflow 文件中的 `ORG/ace-assistant` 替换为实际的组织/仓库路径：

```bash
sed -i 's|ORG/ace-assistant|your-org/ace-assistant|g' \
  .github/workflows/ace-dispatch.yml \
  .github/workflows/ace-fix.yml \
  .github/workflows/ace-review.yml
```

### 3. 添加配置文件

在你的仓库中创建 `.github/ace-config.json`。完整示例见 `templates/ace-config.example.json`。

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
| `GH_PAT` | 具有 repo + workflow 权限的 GitHub Personal Access Token | 是 |

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
│     ace-dispatch ├──────────────────►│     ace-dispatch.yml  │
│     ace-fix      ├──────────────────►│     ace-fix.yml       │
│     ace-review   ├──────────────────►│     ace-review.yml    │
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

### ace-dispatch（可复用工作流）

接收序列化的事件数据并执行：
- **Issue 分诊**：AI 分析 Issue，分类并路由至修复
- **ChatOps**：解析评论中的 `/ace fix`、`/ace review` 命令
- **PR 调度**：将 PR 事件路由至审查工作流
- **手动调度**：通过 `workflow_dispatch` 直接路由

**输出**：`route_to`（`fix` | `review` | `none`）和 `route_params`（JSON）

### ace-fix（可复用工作流）

执行 AI 驱动的代码修复：
1. 解析 Issue/PR 上下文
2. 创建工作分支
3. 运行 OpenCode AI Agent 生成修复代码
4. 提交变更并创建/更新 PR
5. 可选：修复完成后自动触发审查

### ace-review（可复用工作流）

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
| ace-dispatch | `contents: read`、`issues: write`、`pull-requests: write`、`actions: write` |
| ace-fix | `contents: write`、`issues: write`、`pull-requests: write`、`actions: write` |
| ace-review | `contents: read`、`issues: write`、`pull-requests: write`、`actions: write` |

## 版本固定

Caller Workflow 应固定到主版本 tag：

```yaml
uses: your-org/ace-assistant/.github/workflows/ace-fix.yml@v1
```

这样 ace-assistant 的非破坏性更新（Bug 修复、功能改进）会自动生效，无需修改 Caller Workflow。

### `v1` tag 从哪里来、如何更新

`v1` 是仓库维护者手动创建和维护的 **Git tag（主版本别名）**，不是 GitHub Actions 自动生成。

推荐发布流程：

```bash
# 1) 先创建不可变的具体版本 tag
git tag -a v1.0.0 -m "Release v1.0.0"

# 2) 再移动主版本别名 v1 到该版本
git tag -fa v1 -m "Move v1 to v1.0.0"

# 3) 推送到远端
git push origin v1.0.0
git push origin v1 --force
```

说明：
- 外部仓库若使用 `@v1`，通常**无需修改**，后续运行会自动跟随到新的 `v1` 指向。
- 外部仓库若固定到 `@v1.0.0` 或 commit SHA，则需要手动更新引用才会升级。
- 建议始终同时保留不可变 tag（如 `v1.0.0`），便于回滚与审计。

## 目录结构

```
.github/
  workflows/         # 可复用工作流（workflow_call）
    ace-dispatch.yml  # Issue 分诊 + 事件路由
    ace-fix.yml       # AI 代码修复
    ace-review.yml    # AI PR 审查
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
  caller-dispatch.yml
  caller-fix.yml
  caller-review.yml
  ace-config.example.json
tests/
  ci/                # CI 脚本测试套件
```

## 开发指南

### 前置要求

- Python 3.12+
- PyYAML（`pip install pyyaml`）

### 运行测试

```bash
pip install pytest pyyaml
PYTHONPATH=. python -m pytest tests/ -v
```

### 脚本使用

所有 CI 脚本均为纯标准库 Python（`validate_workflow_structure.py` 除外，需要 PyYAML）。以模块方式调用：

```bash
python -m scripts.ci.build_prompt --help
python -m scripts.ci.parse_issue_form --help
```
