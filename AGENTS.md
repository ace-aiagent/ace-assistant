# 项目概要

`ace-assistant` 是一套可复用的 GitHub Actions AI 工作流模板，用于在业务仓库中实现自动化 **Issue 分诊、代码修复与 PR 审查**。

核心形态：
- 业务仓库通过 caller workflow 接入；
- `ace-assistant` 仓库提供可复用 workflow、composite actions 与 CI 脚本；
- 通过统一配置（`ace-config.json`）与密钥，实现可复制的 AI 工程化流程。

# 代码风格

## 必须严格遵守的准则

- 严格使用 TDD 开发范式，每个功能都要先写测试，运行测试，失败后再写实现，直到测试通过
- commit 内容使用中文编写, 提交小的 commit, 不要提交大而全的 commit.
- 只 commit 自己修改的文件, 不要 commit 或者回退非自己修改的文件.
