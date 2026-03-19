# 项目概要

`ace-assistant` 是一套可复用的 GitHub Actions AI 工作流模板，用于在业务仓库中实现自动化 **Issue 分诊、代码修复与 PR 审查**。

核心形态：
- 业务仓库通过 caller workflow 接入；
- `ace-assistant` 仓库提供可复用 workflow、composite actions 与 CI 脚本；
- 通过统一配置（`ace-config.json`）与密钥，实现可复制的 AI 工程化流程。

# 技术栈 & 命令

## 技术栈

- **Python**: 3.12+（CI 脚本使用纯标准库 Python，仅 `validate_workflow_structure.py` 需要 PyYAML）
- **GitHub Actions**: workflow_call 可复用工作流、composite actions
- **PyYAML**: 用于 workflow 结构验证

## 常用命令

```bash
# 安装测试依赖
pip install pytest pyyaml

# 运行测试
PYTHONPATH=. python -m pytest tests/ -v

# 调用 CI 脚本（以模块方式运行）
python -m scripts.ci.build_prompt --help
python -m scripts.ci.parse_issue_form --help
```

# **不可妥协**

- 严格使用 TDD 开发范式，每个功能都要先写测试，运行测试，失败后再写实现，直到测试通过
- commit 内容使用中文编写, 提交小的 commit, 不要提交大而全的 commit
- 只 commit 自己修改的文件, 不要 commit 或者回退非自己修改的文件
- commit 遵循 Angular Commit Message Standard, 格式为 `<type>(<scope>): <subject>`
    - type: 可选值为 `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`
- 新建分支或 worktree 的名称要以 `feature/`, `refactor/`, `fix/` 等开头, 不要使用其他前缀
