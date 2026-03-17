# ace-assistant

Reusable AI CI workflows for GitHub Actions. Provides AI-powered issue triage, automated code fixing, and PR review as centralized, reusable workflows that any repository can adopt.

## Features

- **AI Dispatch** — Listens to issues, comments, and PRs; triages via AI; routes to fix or review
- **AI Fix** — Creates branches, generates fixes using AI, commits and opens PRs
- **AI Review** — Reviews PRs with AI, approves or requests changes, supports auto-loop (review → fix → review)

## Quick Start

### 1. Copy caller workflows

Copy the 3 caller workflow templates from `templates/` to your repository's `.github/workflows/`:

```bash
# From your business repository root
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-dispatch.yml \
  -o .github/workflows/ace-dispatch.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-fix.yml \
  -o .github/workflows/ace-fix.yml
curl -sL https://raw.githubusercontent.com/ORG/ace-assistant/v1/templates/caller-review.yml \
  -o .github/workflows/ace-review.yml
```

### 2. Replace placeholder

In all 3 workflow files, replace `ORG/ace-assistant` with the actual org/repo path:

```bash
sed -i 's|ORG/ace-assistant|your-org/ace-assistant|g' \
  .github/workflows/ace-dispatch.yml \
  .github/workflows/ace-fix.yml \
  .github/workflows/ace-review.yml
```

### 3. Add configuration

Create `.github/ace-config.json` in your repository. See `templates/ace-config.example.json` for a full example.

Key fields to customize:

| Field | Description |
|-------|-------------|
| `tech_stack.language` | Your project's primary language |
| `tech_stack.package_manager` | Package manager (npm, uv, cargo, etc.) |
| `tech_stack.test_command` | Command to run tests |
| `tech_stack.type_check_command` | Command for type checking (optional) |
| `bot.name` | Git commit author name for AI |
| `bot.email` | Git commit author email for AI |
| `branch.prefix` | Branch naming prefix for AI-created branches |
| `chatops.command_prefix` | ChatOps command prefix (default: `ace`) |

### 4. Configure secrets

Add these secrets to your repository (Settings → Secrets and variables → Actions):

| Secret | Description | Required |
|--------|-------------|----------|
| `OPENCODE_AUTH_JSON_B64` | Base64-encoded OpenCode auth JSON | Yes |
| `GH_PAT` | GitHub Personal Access Token with `repo` + `workflow` scope | Yes |

The PAT needs `repo` and `workflow` permissions to dispatch workflows and manage PRs/issues.

### 5. (Optional) Add issue template

Create `.github/ISSUE_TEMPLATE/bug-report.yml` with form fields that the AI can parse:

- **Title** — Short description of the bug
- **Description** — Detailed reproduction steps
- **Base branch** — Branch to create the fix from (default: `main`)

## Architecture

```
Business Repo                          ace-assistant Repo
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

**Caller workflows** (in your repo) are thin: they listen to events, pass inputs to reusable workflows, and handle routing based on outputs.

**Reusable workflows** (in this repo) contain all AI logic, composite actions, and Python scripts.

## Workflow Details

### ace-dispatch (Reusable)

Accepts serialized event data and performs:
- **Issue triage**: AI analyzes the issue, classifies it, routes to fix
- **ChatOps**: Parses `/ace fix`, `/ace review` commands from comments
- **PR dispatch**: Routes PR events to review workflow
- **Manual dispatch**: Direct routing via `workflow_dispatch`

**Outputs**: `route_to` (`fix` | `review` | `none`) and `route_params` (JSON)

### ace-fix (Reusable)

Performs AI-powered code fixes:
1. Parses issue/PR context
2. Creates a working branch
3. Runs OpenCode AI agent to generate fix
4. Commits changes and creates/updates PR
5. Optionally dispatches review after fix

### ace-review (Reusable)

Performs AI-powered PR review:
1. Fetches PR diff and context
2. Runs OpenCode AI agent for review
3. Submits review (approve / request changes / comment)
4. Supports multi-round review loops

**Outputs**: `needs_fix` and `fix_params` for auto-loop

## Required Permissions

Caller workflows must declare these permissions:

| Workflow | Permissions |
|----------|-------------|
| ace-dispatch | `contents: read`, `issues: write`, `pull-requests: write`, `actions: write` |
| ace-fix | `contents: write`, `issues: write`, `pull-requests: write`, `actions: write` |
| ace-review | `contents: read`, `issues: write`, `pull-requests: write`, `actions: write` |

## Version Pinning

Pin caller workflows to a major version tag:

```yaml
uses: your-org/ace-assistant/.github/workflows/ace-fix.yml@v1
```

This allows non-breaking updates (bug fixes, improvements) without changing caller workflows.

### How `v1` Works

`v1` is a maintained major-version tag, not an automatically generated GitHub Actions concept.

Release flow:

```bash
# 1) Create an immutable concrete version tag first
git tag -a v1.0.0 -m "Release v1.0.0"

# 2) Move the major alias v1 to that version
git tag -fa v1 -m "Move v1 to v1.0.0"

# 3) Push both tags to remote
git push origin v1.0.0
git push origin v1 --force
```

- Callers using `@v1` should expect backward-compatible `1.x` updates.
- Callers that need stricter change control can pin a concrete release tag or commit SHA instead.
- Repository maintainers should keep `v1` pointing at the latest stable `1.x` release.

## Directory Structure

```
.github/
  workflows/         # Reusable workflows (workflow_call)
    ace-dispatch.yml  # Issue triage + event routing
    ace-fix.yml       # AI code fixing
    ace-review.yml    # AI PR review
  actions/           # Composite actions
    ace-worker-bootstrap/  # Dual checkout + environment setup
    setup-opencode/       # OpenCode auth configuration
    configure-git/        # Git identity setup
    git-commit-push/      # Commit and push changes
    load-error-config/    # Load error recovery config
    ensure-labels/        # Create labels if missing
    upsert-marker-comment/ # Create/update marker comments
    check-failure-count/  # Guard against repeated failures
scripts/
  ci/                # Python CI scripts (stdlib-only)
templates/           # Caller workflow templates
  caller-dispatch.yml
  caller-fix.yml
  caller-review.yml
  ace-config.example.json
tests/
  ci/                # Test suite for CI scripts
```

## Development

### Prerequisites

- Python 3.12+
- PyYAML (`pip install pyyaml`)

### Running Tests

```bash
pip install pytest pyyaml
PYTHONPATH=. python -m pytest tests/ -v
```

### Scripts

All CI scripts are stdlib-only Python (except `validate_workflow_structure.py` which requires PyYAML). They are invoked as modules:

```bash
python -m scripts.ci.build_prompt --help
python -m scripts.ci.parse_issue_form --help
```
