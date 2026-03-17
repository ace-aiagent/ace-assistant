from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.ci._config import (
    AceConfig,
    BranchConfig,
    WorkflowValidationConfig,
    get_branch_prefix,
    get_detection_patterns,
    get_environment_block,
    get_workflow_validation,
    load_ace_config,
    validate_branch_config,
)


def _full_config_payload() -> dict[str, Any]:
    return {
        "tech_stack": {
            "language": "Python 3.12",
            "package_manager": "uv",
            "test_command": "uv run pytest",
            "type_check_command": "uv run basedpyright --level error",
            "runner": "ubuntu-latest",
        },
        "bot": {
            "name": "ace-uai[bot]",
            "email": "ace-uai[bot]@users.noreply.github.com",
        },
        "branch": {
            "prefix": "ace/fix/issue",
            "detection_patterns": ["ace/*", "fix/*", "issue-*"],
        },
        "labels": {
            "triaging": {
                "color": "1D76DB",
                "description": "Ace is triaging this issue",
            },
            "confirmed": {
                "color": "0E8A16",
                "description": "Ace confirmed this is a real bug",
            },
            "not-a-bug": {
                "color": "B60205",
                "description": "Ace thinks this is not a bug",
            },
            "needs-human": {
                "color": "FBCA04",
                "description": "Ace needs human input or failed to proceed",
            },
            "fixing": {
                "color": "5319E7",
                "description": "Ace is preparing a fix",
            },
            "pr-opened": {
                "color": "0052CC",
                "description": "Ace opened a PR for this issue",
            },
            "managed": {
                "color": "5319E7",
                "description": "PR is managed by Ace loop",
            },
            "reviewing": {
                "color": "1D76DB",
                "description": "Ace is reviewing the PR",
            },
            "changes-requested": {
                "color": "D93F0B",
                "description": "Ace review requested changes",
            },
            "review-approved": {
                "color": "0E8A16",
                "description": "Ace review approved the PR",
            },
            "loop-exceeded": {
                "color": "B60205",
                "description": "Ace review/fix loop exceeded max rounds",
            },
        },
        "review": {"max_rounds": 3},
        "ci_paths": {
            "scripts": ["scripts/ci/*", "scripts/__init__.py", "scripts/ci/__init__.py"],
            "actions": [".github/actions/*"],
        },
        "error_recovery": {
            "max_consecutive_failures": 3,
            "auto_label_on_max_failures": True,
        },
        "workflow_validation": {
            "required_inputs": {
                "ace-dispatch.yml": ["target_type", "target_number", "action"],
                "ace-fix.yml": ["target_type", "target_number", "auto_loop", "extra_prompt", "triage_json"],
                "ace-review.yml": ["pr_number", "auto_loop", "extra_prompt"],
            },
            "expected_concurrency_prefixes": {
                "ace-dispatch.yml": "ace-dispatch-",
                "ace-fix.yml": "ace-fix-",
                "ace-review.yml": "ace-review-",
            },
            "required_markers": ["ace-pr-meta", "ace-review-context"],
        },
        "chatops": {
            "command_prefix": "ace",
            "allowed_associations": ["OWNER", "MEMBER", "COLLABORATOR"],
        },
    }


def test_load_full_config_success(write_json: Callable[[str, Any], Path]) -> None:
    config_file = write_json("ace-config.json", _full_config_payload())
    config = load_ace_config(str(config_file))

    assert config.tech_stack.runner == "ubuntu-latest"
    assert config.bot.email == "ace-uai[bot]@users.noreply.github.com"
    assert config.branch.detection_patterns == ["ace/*", "fix/*", "issue-*"]
    assert config.labels["triaging"].color == "1D76DB"
    assert config.workflow_validation.required_markers == ["ace-pr-meta", "ace-review-context"]


def test_missing_config_file_returns_defaults(tmp_path: Path) -> None:
    config = load_ace_config(str(tmp_path / "missing.json"))

    assert config.bot.name == "ace-uai[bot]"
    assert config.branch.prefix == "ace/fix/issue"
    assert config.review.max_rounds == 3


def test_empty_json_raises_when_tech_stack_missing(write_json: Callable[[str, Any], Path]) -> None:
    config_file = write_json("ace-config.json", {})

    with pytest.raises(ValueError, match="tech_stack"):
        load_ace_config(str(config_file))


def test_malformed_json_raises_with_path(write_text: Callable[[str, str], Path]) -> None:
    config_file = write_text("ace-config.json", "{not-json")

    with pytest.raises(ValueError) as exc_info:
        load_ace_config(str(config_file))

    assert str(config_file) in str(exc_info.value)


def test_partial_config_merges_with_defaults(write_json: Callable[[str, Any], Path]) -> None:
    config_file = write_json(
        "ace-config.json",
        {
            "tech_stack": {
                "language": "Python 3.13",
                "package_manager": "uv",
                "test_command": "uv run pytest -q",
                "type_check_command": "uv run basedpyright --level error",
                "runner": "ubuntu-24.04",
            }
        },
    )
    config = load_ace_config(str(config_file))

    assert config.tech_stack.language == "Python 3.13"
    assert config.tech_stack.runner == "ubuntu-24.04"
    assert config.bot.name == "ace-uai[bot]"
    assert config.chatops.command_prefix == "ace"


def test_unknown_top_level_fields_emit_warning(write_json: Callable[[str, Any], Path], caplog: pytest.LogCaptureFixture) -> None:
    payload = _full_config_payload()
    payload["future_field"] = {"enabled": True}
    config_file = write_json("ace-config.json", payload)

    with caplog.at_level("WARNING"):
        config = load_ace_config(str(config_file))

    assert config.tech_stack.language == "Python 3.12"
    assert "Unknown ace config fields" in caplog.text
    assert "future_field" in caplog.text


def test_get_environment_block_format(write_json: Callable[[str, Any], Path]) -> None:
    config_file = write_json("ace-config.json", _full_config_payload())
    config = load_ace_config(str(config_file))

    expected = (
        "Environment:\n"
        "- Python 3.12, uv package manager (run tests with: uv run pytest)\n"
        "- GitHub Actions ubuntu-latest runner\n"
        "- jq, git, gh CLI available\n"
        "- Do NOT install additional tools"
    )
    assert get_environment_block(config) == expected


def test_ace_config_path_env_override_default(
    write_json: Callable[[str, Any], Path],
    set_ci_env: Callable[..., None],
) -> None:
    config_file = write_json(
        "custom-config.json",
        {
            "tech_stack": {
                "language": "Python 3.13",
                "package_manager": "uv",
                "test_command": "uv run pytest",
                "type_check_command": "uv run basedpyright --level error",
                "runner": "ubuntu-latest",
            }
        },
    )
    set_ci_env(ACE_CONFIG_PATH=str(config_file))
    config = load_ace_config()

    assert config.tech_stack.language == "Python 3.13"


def test_validate_branch_config_warns_on_prefix_mismatch() -> None:
    config = AceConfig(
        tech_stack=load_ace_config(config_path="/path/does/not/exist").tech_stack,
        bot=load_ace_config(config_path="/path/does/not/exist").bot,
        branch=BranchConfig(prefix="feature/work", detection_patterns=["bugfix/*", "hotfix/*"]),
        labels=load_ace_config(config_path="/path/does/not/exist").labels,
        review=load_ace_config(config_path="/path/does/not/exist").review,
        ci_paths=load_ace_config(config_path="/path/does/not/exist").ci_paths,
        error_recovery=load_ace_config(config_path="/path/does/not/exist").error_recovery,
        workflow_validation=load_ace_config(config_path="/path/does/not/exist").workflow_validation,
        chatops=load_ace_config(config_path="/path/does/not/exist").chatops,
    )

    warnings = validate_branch_config(config)

    assert len(warnings) == 1
    assert "feature/work" in warnings[0]


def test_helper_functions_return_expected_types(write_json: Callable[[str, Any], Path]) -> None:
    config_file = write_json("ace-config.json", _full_config_payload())
    config = load_ace_config(str(config_file))

    assert get_branch_prefix(config) == "ace/fix/issue"
    assert get_detection_patterns(config) == ["ace/*", "fix/*", "issue-*"]
    assert isinstance(get_workflow_validation(config), WorkflowValidationConfig)
