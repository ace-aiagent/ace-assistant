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
            workflow_dir / "ace-dispatch.yml",
            workflow_dir / "ace-fix.yml",
            workflow_dir / "ace-review.yml",
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
    def test_reusable_workflow_does_not_define_top_level_permissions(
        self, workflow_file: Path
    ) -> None:
        """Reusable workflows (workflow_call) must NOT define top-level permissions.

        Permissions are the caller's responsibility; defining them here would
        override the caller's settings and break least-privilege in consumer repos.
        """
        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert "permissions" not in data, (
            f"{workflow_file.name} must not define top-level permissions; "
            "reusable workflows inherit permissions from the caller"
        )

    @pytest.mark.parametrize(
        "workflow_file", get_ai_workflow_files(), ids=lambda p: p.name
    )
    def test_workflow_script_references_exist(self, workflow_file: Path) -> None:
        """Test that run: steps referencing scripts/ci modules point to existing files."""
        root = get_project_root()

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        scripts_referenced: set[str] = set()
        jobs = data.get("jobs", {})

        for _job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue

                run_script = step.get("run")
                if not isinstance(run_script, str):
                    continue

                # Match module invocations: python -m scripts.ci.xxx
                for match in re.finditer(r"python\s+-m\s+scripts\.ci\.(\w+)", run_script):
                    scripts_referenced.add(match.group(1) + ".py")

                # Also match direct file invocations: python scripts/ci/xxx.py
                for match in re.finditer(r"python\s+scripts/ci/(\w+\.py)", run_script):
                    scripts_referenced.add(match.group(1))

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
        """Test that uses: steps referencing composite actions point to existing action directories."""
        root = get_project_root()

        with open(workflow_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        actions_referenced: set[str] = set()
        jobs = data.get("jobs", {})

        for _job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue

                uses = step.get("uses", "")
                if not isinstance(uses, str):
                    continue

                # Match local relative refs: ./.github/actions/xxx
                match = re.match(r"\./.github/actions/([^/]+)", uses)
                if match:
                    actions_referenced.add(match.group(1))
                    continue

                # Match checkout-path relative refs: ./.ace-assistant/.github/actions/xxx
                match = re.match(r"\./\.ace-assistant/\.github/actions/([^/]+)", uses)
                if match:
                    actions_referenced.add(match.group(1))
                    continue

                # Match cross-repo refs: ace0-uai/ace-assistant/.github/actions/xxx@ref
                match = re.match(r"ace0-uai/ace-assistant/\.github/actions/([^/@]+)", uses)
                if match:
                    actions_referenced.add(match.group(1))

        for action_name in actions_referenced:
            action_dir = root / ".github" / "actions" / action_name
            action_file = action_dir / "action.yml"
            assert action_dir.exists(), (
                f"Action directory referenced in {workflow_file.name} does not exist: .github/actions/{action_name}"
            )
            assert action_file.exists(), (
                f"action.yml missing for action referenced in {workflow_file.name}: .github/actions/{action_name}/action.yml"
            )

    def test_ai_fix_cleanup_files_do_not_remove_tracked_actions_or_scripts(
        self,
    ) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "ace-fix.yml"

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
