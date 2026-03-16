from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


def get_project_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).resolve().parents[2]


def get_ai_workflow_files() -> list[Path]:
    """Get all AI workflow YAML files."""
    root = get_project_root()
    workflow_dir = root / ".github" / "workflows"
    return sorted(
        [
            workflow_dir / "ai-dispatch.yml",
            workflow_dir / "ai-fix.yml",
            workflow_dir / "ai-review.yml",
        ]
    )


def get_composite_action_files() -> list[Path]:
    """Get all composite action.yml files."""
    root = get_project_root()
    actions_dir = root / ".github" / "actions"
    return sorted(actions_dir.glob("*/action.yml"))


def get_scripts_ci_python_files() -> list[Path]:
    """Get all Python files in scripts/ci directory."""
    root = get_project_root()
    scripts_dir = root / "scripts" / "ci"
    return sorted(scripts_dir.glob("*.py"))


@pytest.mark.skip(reason="workflow YAML files not yet migrated, will be created in Tasks 7-9")
class TestYamlWorkflowValidation:
    """Validation tests for AI workflow YAML files."""

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_yaml_is_valid_syntax(self, workflow_file: Path) -> None:
        """Test that all AI workflow YAML files can be parsed."""
        assert workflow_file.exists(), f"Workflow file does not exist: {workflow_file}"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data is not None, f"YAML file is empty or invalid: {workflow_file}"
        assert isinstance(data, dict), f"YAML root must be a dict: {workflow_file}"

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_has_required_keys(self, workflow_file: Path) -> None:
        """Test that all workflows have required top-level keys: name, on, jobs."""
        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # PyYAML converts unquoted 'on:' to boolean True
        assert "name" in data, f"Missing 'name' in {workflow_file.name}"
        assert True in data, (
            f"Missing 'on:' trigger (PyYAML parses as True key) in {workflow_file.name}"
        )
        assert "jobs" in data, f"Missing 'jobs' in {workflow_file.name}"

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_defines_permissions(self, workflow_file: Path) -> None:
        """Test that workflows define permissions (top-level or in every job)."""
        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        has_top_level_permissions = "permissions" in data

        if not has_top_level_permissions:
            jobs = data.get("jobs", {})
            for job_name, job_config in jobs.items():
                if isinstance(job_config, dict):
                    assert "permissions" in job_config, (
                        f"Job '{job_name}' in {workflow_file.name} missing permissions"
                    )

        # If we reach here, either top-level permissions exist or all jobs have permissions
        assert has_top_level_permissions or all(
            isinstance(job_config, dict) and "permissions" in job_config
            for job_config in data.get("jobs", {}).values()
        )

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_script_references_exist(self, workflow_file: Path) -> None:
        """Test that run: steps referencing python scripts/ci/*.py point to existing files."""
        root = get_project_root()

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Collect all 'run:' steps that reference scripts/ci/*.py
        scripts_referenced = set()
        jobs = data.get("jobs", {})

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue

                run_script = step.get("run")
                if isinstance(run_script, str):
                    # Find all patterns: python scripts/ci/xxx.py
                    matches = re.findall(r"python\s+scripts/ci/(\w+\.py)", run_script)
                    scripts_referenced.update(matches)

        # Verify each referenced script exists
        for script_name in scripts_referenced:
            script_path = root / "scripts" / "ci" / script_name
            assert script_path.exists(), (
                f"Script referenced in {workflow_file.name} does not exist: scripts/ci/{script_name}"
            )

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_composite_action_references_exist(
        self, workflow_file: Path
    ) -> None:
        """Test that uses: ./.github/actions/* steps point to existing action directories."""
        root = get_project_root()

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Collect all 'uses:' steps that reference ./.github/actions/
        actions_referenced = set()
        jobs = data.get("jobs", {})

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue

                uses = step.get("uses", "")
                if isinstance(uses, str) and uses.startswith("./.github/actions/"):
                    # Extract action name: ./.github/actions/action-name/... → action-name
                    match = re.match(r"\./.github/actions/([^/]+)", uses)
                    if match:
                        actions_referenced.add(match.group(1))

        # Verify each referenced action directory exists with action.yml
        for action_name in actions_referenced:
            action_dir = root / ".github" / "actions" / action_name
            action_file = action_dir / "action.yml"
            assert action_dir.exists(), (
                f"Action directory referenced in {workflow_file.name} does not exist: .github/actions/{action_name}"
            )
            assert action_file.exists(), (
                f"action.yml missing for action referenced in {workflow_file.name}: .github/actions/{action_name}/action.yml"
            )

    def test_ai_fix_has_cache_and_restore_around_branch_checkout(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ai-fix.yml"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        steps = data["jobs"]["fix"]["steps"]
        step_names = [step.get("name", "") for step in steps if isinstance(step, dict)]

        assert "Save CI assets before checkout" in step_names
        assert "Restore CI assets after checkout" in step_names
        assert "Save CI assets before PR checkout" in step_names
        assert "Restore CI assets after PR checkout" in step_names

    def test_ai_review_has_cache_and_restore_around_pr_checkout(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ai-review.yml"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        steps = data["jobs"]["review"]["steps"]
        step_names = [step.get("name", "") for step in steps if isinstance(step, dict)]

        assert "Save CI assets before checkout" in step_names
        assert "Restore CI assets after checkout" in step_names

    def test_ai_fix_cache_restore_order_guards_post_checkout_steps(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ai-fix.yml"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        steps = data["jobs"]["fix"]["steps"]
        step_index = {
            step.get("name", ""): idx
            for idx, step in enumerate(steps)
            if isinstance(step, dict)
        }

        assert (
            step_index["Save CI assets before checkout"]
            < step_index["Create issue fix branch"]
        )
        assert (
            step_index["Create issue fix branch"]
            < step_index["Restore CI assets after checkout"]
        )
        assert (
            step_index["Restore CI assets after checkout"]
            < step_index["Build issue fix prompt"]
        )

        assert (
            step_index["Save CI assets before PR checkout"]
            < step_index["Checkout PR head branch"]
        )
        assert (
            step_index["Checkout PR head branch"]
            < step_index["Restore CI assets after PR checkout"]
        )
        assert (
            step_index["Restore CI assets after PR checkout"]
            < step_index["PR idempotency guard"]
        )

    def test_ai_fix_cleanup_files_do_not_remove_tracked_actions_or_scripts(
        self,
    ) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ai-fix.yml"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        steps = data["jobs"]["fix"]["steps"]
        commit_steps = [
            step
            for step in steps
            if isinstance(step, dict)
            and step.get("name")
            in {"Commit and push issue fix", "Commit and push PR retry fix"}
        ]

        assert len(commit_steps) == 2

        forbidden_prefixes = (".github/actions/", "scripts/ci/")
        for step in commit_steps:
            cleanup_files = step.get("with", {}).get("cleanup-files", "")
            assert isinstance(cleanup_files, str)
            for entry in cleanup_files.split():
                assert not entry.startswith(forbidden_prefixes), (
                    f"{step.get('name')} cleanup-files must not include tracked path: {entry}"
                )

    def test_ai_review_cache_restore_order_guards_post_checkout_steps(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ai-review.yml"

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        steps = data["jobs"]["review"]["steps"]
        step_index = {
            step.get("name", ""): idx
            for idx, step in enumerate(steps)
            if isinstance(step, dict)
        }

        assert (
            step_index["Save CI assets before checkout"]
            < step_index["Checkout PR head branch"]
        )
        assert (
            step_index["Checkout PR head branch"]
            < step_index["Restore CI assets after checkout"]
        )
        assert (
            step_index["Restore CI assets after checkout"]
            < step_index["Build review prompt"]
        )


@pytest.mark.skip(reason="composite action files not yet migrated, will be created in Tasks 5-6")
class TestCompositeActionValidation:
    """Validation tests for composite action.yml files."""

    @pytest.mark.parametrize(
        "action_file", get_composite_action_files(), ids=lambda p: p.parent.name
    )
    def test_composite_action_yaml_is_valid_syntax(self, action_file: Path) -> None:
        """Test that all action.yml files can be parsed."""
        assert action_file.exists(), f"Action file does not exist: {action_file}"

        with open(action_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data is not None, f"YAML file is empty or invalid: {action_file}"
        assert isinstance(data, dict), f"YAML root must be a dict: {action_file}"

    @pytest.mark.parametrize(
        "action_file", get_composite_action_files(), ids=lambda p: p.parent.name
    )
    def test_composite_action_has_required_keys(self, action_file: Path) -> None:
        """Test that all action.yml files have required keys: name, description, runs."""
        with open(action_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "name" in data, f"Missing 'name' in {action_file}"
        assert "description" in data, f"Missing 'description' in {action_file}"
        assert "runs" in data, f"Missing 'runs' in {action_file}"

    def test_git_commit_push_cleanup_supports_directories(self) -> None:
        action_file = (
            get_project_root()
            / ".github"
            / "actions"
            / "git-commit-push"
            / "action.yml"
        )

        with open(action_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        run_script = data["runs"]["steps"][0]["run"]

        assert 'if [[ -d "$file" ]]' in run_script
        assert 'rm -rf "$file"' in run_script
        assert 'rm -f "$file"' in run_script
