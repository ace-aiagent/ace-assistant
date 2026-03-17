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
            templates_dir / "caller-dispatch.yml",
            templates_dir / "caller-fix.yml",
            templates_dir / "caller-review.yml",
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
            ("caller-dispatch.yml", "ORG/ace-assistant/.github/workflows/ace-dispatch.yml@v1"),
            ("caller-fix.yml", "ORG/ace-assistant/.github/workflows/ace-fix.yml@v1"),
            ("caller-review.yml", "ORG/ace-assistant/.github/workflows/ace-review.yml@v1"),
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
        template_path = get_project_root() / "templates" / "caller-dispatch.yml"
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


class TestCallerReviewTemplateFixParamsSafety:
    def test_trigger_fix_parses_fix_params_without_shell_single_quote_embedding(self) -> None:
        template_path = get_project_root() / "templates" / "caller-review.yml"
        content = template_path.read_text(encoding="utf-8")

        assert "FIX_PARAMS: ${{ needs.review.outputs.fix_params }}" in content
        assert "RAW_FIX_PARAMS=" in content
        assert "SAFE_FIX_PARAMS=" in content
        assert "PARSE_OK=false" in content
        assert "DOUBLE_INNER=" in content
        assert "fromJSON(needs.review.outputs.fix_params)" not in content


class TestAceConfigExampleJson:
    def test_ace_config_example_is_valid_json(self) -> None:
        config_path = get_project_root() / "templates" / "ace-config.example.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "tech_stack" in data
        assert "bot" in data
        assert "branch" in data
        assert "labels" in data
