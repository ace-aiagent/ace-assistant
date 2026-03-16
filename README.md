# coding-agent

Reusable AI CI workflows for GitHub Actions. This repository provides a collection of composable, workflow-callable GitHub Actions and supporting infrastructure for automating code review, testing, and deployment tasks using AI-driven logic.

## Directory Structure

```
.github/
  workflows/          # GitHub Actions workflows (workflow_call templates)
  actions/            # Custom GitHub Actions (composite actions, Docker actions)
scripts/
  ci/                 # CI automation scripts (Python, shell utilities)
templates/            # Reusable templates for workflows, actions, and configuration
tests/
  ci/                 # Tests for CI scripts and automation logic
```

## Getting Started

This repository serves as a centralized source for reusable CI workflows. Workflows are designed to be called from other repositories via the GitHub Actions `workflow_call` trigger.

## Development

All scripts use Python 3.x with no external dependencies (stdlib only) to minimize installation friction.
