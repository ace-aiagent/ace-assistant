from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_template_workflow_files() -> list[Path]:
    templates_dir = get_project_root() / "templates"
    return sorted(
        [
            templates_dir / "dispatch.yml",
            templates_dir / "fix.yml",
            templates_dir / "review.yml",
        ]
    )


class TestTemplateYamlValidation:
    @pytest.mark.parametrize("workflow_file", get_template_workflow_files(), ids=lambda p: p.name)
    def test_template_workflow_yaml_is_valid(self, workflow_file: Path) -> None:
        assert workflow_file.exists(), f"Template workflow file does not exist: {workflow_file}"
        data = yaml.safe_load(workflow_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"YAML root must be a dict: {workflow_file.name}"

    @pytest.mark.parametrize(
        ("workflow_name", "expected_use"),
        [
        ("dispatch.yml", "ORG/ace-assistant/.github/workflows/reusable-dispatch.yml@v1"),
        ("fix.yml", "ORG/ace-assistant/.github/workflows/reusable-fix.yml@v1"),
        ("review.yml", "ORG/ace-assistant/.github/workflows/reusable-review.yml@v1"),
        ],
    )
    def test_template_workflow_keeps_reusable_workflow_reference(
        self, workflow_name: str, expected_use: str
    ) -> None:
        workflow_path = get_project_root() / "templates" / workflow_name
        data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        jobs = data.get("jobs", {})
        first_job = next(iter(jobs.values()))
        assert isinstance(first_job, dict)
        assert first_job.get("uses") == expected_use


class TestCallerDispatchTemplateRouteParamsSafety:
    def test_route_jobs_validate_and_parse_route_params_via_jq(self) -> None:
        template_path = get_project_root() / "templates" / "dispatch.yml"
        content = template_path.read_text(encoding="utf-8")

        # Check env var setup
        assert "ROUTE_PARAMS: ${{ needs.dispatch.outputs.route_params }}" in content
        
        # Check parsing variables
        assert "RAW_ROUTE_PARAMS=\"${ROUTE_PARAMS:-}\"" in content
        assert "SAFE_ROUTE_PARAMS='{}'" in content
        assert "PARSE_OK=false" in content
        
        # Check 3-layer parsing logic
        assert "jq -e 'type == \"object\"'" in content
        assert "jq -e 'type == \"string\"'" in content
        assert "DOUBLE_INNER=" in content
        
        # Check unified guard with error exit
        assert "if [[ -z \"$PR_NUMBER\" ]]; then" in content
        assert "if [[ -z \"$TARGET_NUMBER\" ]]; then" in content
        assert "exit 1" in content
        
        # Check fromJSON is not used (we use manual parsing)
        assert "fromJSON(needs.dispatch.outputs.route_params)" not in content


class TestCallerReviewTemplateDefaults:
    def test_workflow_dispatch_review_defaults_to_manual_loop_mode(self) -> None:
        template_path = get_project_root() / "templates" / "review.yml"
        data = yaml.safe_load(template_path.read_text(encoding="utf-8"))

        workflow_dispatch = data[True]["workflow_dispatch"]
        review_inputs = workflow_dispatch["inputs"]

        assert review_inputs["auto_loop"]["default"] == "false"

    def test_caller_review_template_has_single_review_job(self) -> None:
        template_path = get_project_root() / "templates" / "review.yml"
        content = template_path.read_text(encoding="utf-8")

        assert "trigger-fix:" not in content
        assert "needs.review.outputs.needs_fix" not in content


class TestAceConfigExampleJson:
    def test_ace_config_example_is_valid_json(self) -> None:
        config_path = get_project_root() / "templates" / "config.example.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "tech_stack" in data
        assert "bot" in data
        assert "branch" in data
        assert "labels" not in data
