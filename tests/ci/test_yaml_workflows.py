from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


PROTOCOL_MODE_EXPRESSION = (
    "${{ inputs.ace_protocol_mode || vars.ACE_RESULT_PROTOCOL_MODE || 'legacy' }}"
)
PROTOCOL_DIAGNOSTICS_STEP_NAME = "Show protocol diagnostics on failure"


def get_project_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).resolve().parents[2]


def get_ai_workflow_files() -> list[Path]:
    """Get all AI workflow YAML files."""
    root = get_project_root()
    workflow_dir = root / ".github" / "workflows"
    return sorted(
        [
            workflow_dir / "reusable-dispatch.yml",
            workflow_dir / "reusable-fix.yml",
            workflow_dir / "reusable-review.yml",
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


def load_workflow_yaml(workflow_name: str) -> dict:
    workflow_file = get_project_root() / ".github" / "workflows" / workflow_name
    with open(workflow_file, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_job_steps(workflow_name: str, job_name: str) -> list[dict]:
    workflow = load_workflow_yaml(workflow_name)
    steps = workflow["jobs"][job_name]["steps"]
    assert isinstance(steps, list)
    return [step for step in steps if isinstance(step, dict)]


def get_run_opencode_step_indexes(steps: list[dict]) -> list[int]:
    indexes: list[int] = []
    for index, step in enumerate(steps):
        run_script = step.get("run")
        if isinstance(run_script, str) and "scripts.ci.run_opencode" in run_script:
            indexes.append(index)
    return indexes


def extract_output_file(run_script: str) -> str:
    match = re.search(r"--output-file\s+([^\s]+)", run_script)
    assert match is not None, f"Missing --output-file in run script: {run_script}"
    return match.group(1)


def get_build_prompt_step_indexes(steps: list[dict]) -> list[int]:
    indexes: list[int] = []
    for index, step in enumerate(steps):
        run_script = step.get("run")
        if isinstance(run_script, str) and "scripts.ci.build_prompt" in run_script:
            indexes.append(index)
    return indexes


def get_dispatch_step_indexes(steps: list[dict]) -> list[int]:
    indexes: list[int] = []
    for index, step in enumerate(steps):
        run_script = step.get("run")
        if isinstance(run_script, str) and "gh workflow run" in run_script:
            indexes.append(index)
    return indexes


def assert_run_opencode_steps_have_protocol_mode_env(steps: list[dict]) -> None:
    run_opencode_indexes = get_run_opencode_step_indexes(steps)
    assert run_opencode_indexes, "Expected at least one run_opencode step"

    for index in run_opencode_indexes:
        step = steps[index]
        env = step.get("env")
        assert isinstance(env, dict), f"Step is missing env: {step.get('name')}"
        assert env.get("ACE_RESULT_PROTOCOL_MODE") == PROTOCOL_MODE_EXPRESSION


def assert_protocol_diagnostics_follow_run_opencode_steps(steps: list[dict]) -> None:
    run_opencode_indexes = get_run_opencode_step_indexes(steps)
    assert run_opencode_indexes, "Expected at least one run_opencode step"

    for index in run_opencode_indexes:
        step = steps[index]
        assert index + 1 < len(steps), f"Missing diagnostics step after {step.get('name')}"

        diagnostics_step = steps[index + 1]
        assert diagnostics_step.get("name") == PROTOCOL_DIAGNOSTICS_STEP_NAME
        assert diagnostics_step.get("if") == f"failure() && {step['if']}"
        assert diagnostics_step.get("shell") == "bash"

        diagnostics_run = diagnostics_step.get("run")
        assert isinstance(diagnostics_run, str)
        output_file = extract_output_file(step["run"])
        assert f'DIAG="{output_file}.diagnostics.json"' in diagnostics_run
        assert "if [ -f \"$DIAG\" ]; then" in diagnostics_run
        assert "Protocol diagnostics:" in diagnostics_run
        assert "Protocol error_code:" in diagnostics_run
        assert 'jq -r \' .error_code // "unknown" \' ' not in diagnostics_run
        assert "jq -r '.error_code // \"unknown\"' \"$DIAG\"" in diagnostics_run


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

                # Match cross-repo refs: ace-aiagent/ace-assistant/.github/actions/xxx@ref
                match = re.match(r"ace-aiagent/ace-assistant/\.github/actions/([^/@]+)", uses)
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
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-fix.yml"

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


class TestAceReviewWorkflowMetadataPersistence:
    def test_review_workflow_has_metadata_persistence_gate(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert "- name: Determine metadata persistence mode" in content
        assert "id: meta_mode" in content
        assert 'echo "persist_meta=true" >> "$GITHUB_OUTPUT"' in content
        assert 'echo "persist_meta=false" >> "$GITHUB_OUTPUT"' in content

    def test_review_workflow_meta_comments_are_guarded_by_persistence_mode(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert "steps.meta_mode.outputs.persist_meta == 'true'" in content
        assert "- name: Upsert guard lock meta comment" in content
        assert "- name: Upsert review context comment" in content
        assert "- name: Upsert approval meta comment" in content
        assert "- name: Upsert loop exceeded meta comment" in content
        assert "- name: Upsert fix-requested meta comment" in content
        assert "- name: Upsert manual mode meta comment" in content

    def test_force_reset_upsert_is_guarded_by_persistence_mode(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert 'PERSIST_META: ${{ steps.meta_mode.outputs.persist_meta }}' in content
        assert 'if [[ "$PERSIST_META" == "true" ]]; then' in content

    def test_review_workflow_uses_current_input_auto_loop_for_meta_updates(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        expected = '$( [[ "${{ inputs.auto_loop }}" == "true" ]] && echo true || echo false )'
        assert expected in content
        assert "jq '.auto_loop // true' pr_meta.json" not in content

    def test_review_workflow_rollback_meta_upsert_is_guarded_by_persistence_mode(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert "steps.meta_mode.outputs.persist_meta == 'true' && (failure() || cancelled())" in content

    def test_review_workflow_has_single_fix_dispatch_path(self) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert content.count("- name: Dispatch ace-fix workflow") == 1

    def test_review_workflow_updates_labels_with_github_token_after_changes_requested(
        self,
    ) -> None:
        workflow_file = get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        content = workflow_file.read_text(encoding="utf-8")

        assert "- name: Update labels after changes requested" in content
        assert (
            "steps.review_outcome.outputs.decision == 'CHANGES_REQUESTED'" in content
        )
        assert 'GH_TOKEN: ${{ github.token }}' in content
        assert '--remove-label "ai:reviewing"' in content
        assert '--add-label "ai:changes-requested"' in content


class TestProtocolRolloutControls:
    def test_ace_fix_run_opencode_steps_have_protocol_mode_env(self) -> None:
        steps = get_job_steps("reusable-fix.yml", "fix")

        assert len(get_run_opencode_step_indexes(steps)) == 3
        assert_run_opencode_steps_have_protocol_mode_env(steps)

    def test_ace_review_run_opencode_step_has_protocol_mode_env(self) -> None:
        steps = get_job_steps("reusable-review.yml", "review")

        assert len(get_run_opencode_step_indexes(steps)) == 1
        assert_run_opencode_steps_have_protocol_mode_env(steps)

    def test_ace_fix_has_protocol_diagnostics_steps(self) -> None:
        steps = get_job_steps("reusable-fix.yml", "fix")

        assert steps.count({"name": PROTOCOL_DIAGNOSTICS_STEP_NAME}) == 0
        assert_protocol_diagnostics_follow_run_opencode_steps(steps)

    def test_ace_review_has_protocol_diagnostics_step(self) -> None:
        steps = get_job_steps("reusable-review.yml", "review")

        assert_protocol_diagnostics_follow_run_opencode_steps(steps)

    def test_workflows_expose_protocol_mode_input(self) -> None:
        for workflow_name in ("reusable-fix.yml", "reusable-review.yml"):
            workflow = load_workflow_yaml(workflow_name)
            inputs = workflow[True]["workflow_call"]["inputs"]

            assert "ace_protocol_mode" in inputs
            assert inputs["ace_protocol_mode"] == {
                "description": "Protocol mode override (legacy | dual-read | strict-envelope)",
                "type": "string",
                "required": False,
                "default": "",
            }

    def test_ace_fix_build_prompt_steps_have_protocol_mode_env(self) -> None:
        steps = get_job_steps("reusable-fix.yml", "fix")
        indexes = get_build_prompt_step_indexes(steps)

        assert len(indexes) == 3, f"Expected 3 build_prompt steps, found {len(indexes)}"
        for index in indexes:
            step = steps[index]
            env = step.get("env")
            assert isinstance(env, dict), f"build_prompt step missing env: {step.get('name')}"
            assert env.get("ACE_RESULT_PROTOCOL_MODE") == PROTOCOL_MODE_EXPRESSION

    def test_ace_review_build_prompt_step_has_protocol_mode_env(self) -> None:
        steps = get_job_steps("reusable-review.yml", "review")
        indexes = get_build_prompt_step_indexes(steps)

        assert len(indexes) == 1, f"Expected 1 build_prompt step, found {len(indexes)}"
        step = steps[indexes[0]]
        env = step.get("env")
        assert isinstance(env, dict), f"build_prompt step missing env: {step.get('name')}"
        assert env.get("ACE_RESULT_PROTOCOL_MODE") == PROTOCOL_MODE_EXPRESSION

    def test_ace_fix_dispatch_steps_forward_protocol_mode(self) -> None:
        steps = get_job_steps("reusable-fix.yml", "fix")
        indexes = get_dispatch_step_indexes(steps)

        assert len(indexes) == 2, f"Expected 2 dispatch steps, found {len(indexes)}"
        for index in indexes:
            run_script = steps[index].get("run", "")
            assert "-f ace_protocol_mode=" in run_script, (
                f"Dispatch step missing ace_protocol_mode forwarding:\n{run_script}"
            )

    def test_ace_review_dispatch_step_forwards_protocol_mode(self) -> None:
        steps = get_job_steps("reusable-review.yml", "review")
        indexes = get_dispatch_step_indexes(steps)

        assert len(indexes) == 1, f"Expected 1 dispatch step, found {len(indexes)}"
        run_script = steps[indexes[0]].get("run", "")
        assert "-f ace_protocol_mode=" in run_script, (
            f"Dispatch step missing ace_protocol_mode forwarding:\n{run_script}"
        )

    def test_ace_review_fix_params_includes_protocol_mode(self) -> None:
        content = (
            get_project_root() / ".github" / "workflows" / "reusable-review.yml"
        ).read_text(encoding="utf-8")
        assert 'ace_protocol_mode' in content and 'fix_params' in content, (
            "fix_params JSON must include ace_protocol_mode key"
        )
        assert '"ace_protocol_mode"' in content or r'\"ace_protocol_mode\"' in content, (
            "fix_params JSON must include ace_protocol_mode key"
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
