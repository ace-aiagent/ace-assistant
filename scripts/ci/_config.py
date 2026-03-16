#!/usr/bin/env python3
"""Ace AI CI config loader with immutable dataclass outputs."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = ".github/ace-config.json"


@dataclass(frozen=True)
class TechStackConfig:
    language: str = "Python 3.12"
    package_manager: str = "uv"
    test_command: str = "uv run pytest"
    type_check_command: str = "uv run basedpyright --level error"
    runner: str = "ubuntu-latest"


@dataclass(frozen=True)
class BotConfig:
    name: str = "ace-uai[bot]"
    email: str = "ace-uai[bot]@users.noreply.github.com"


@dataclass(frozen=True)
class BranchConfig:
    prefix: str = "ace/fix/issue"
    detection_patterns: list[str] = field(default_factory=lambda: ["ace/*", "fix/*", "issue-*"])


@dataclass(frozen=True)
class LabelInfo:
    color: str
    description: str


@dataclass(frozen=True)
class ReviewConfig:
    max_rounds: int = 3


@dataclass(frozen=True)
class CiPathsConfig:
    scripts: list[str] = field(default_factory=lambda: ["scripts/ci/*", "scripts/__init__.py", "scripts/ci/__init__.py"])
    actions: list[str] = field(default_factory=lambda: [".github/actions/*"])


@dataclass(frozen=True)
class ErrorRecoveryConfig:
    max_consecutive_failures: int = 3
    auto_label_on_max_failures: bool = True


@dataclass(frozen=True)
class WorkflowValidationConfig:
    required_inputs: dict[str, list[str]] = field(
        default_factory=lambda: {
            "ai-dispatch.yml": ["target_type", "target_number", "action"],
            "ai-fix.yml": ["target_type", "target_number", "auto_loop", "extra_prompt", "triage_json"],
            "ai-review.yml": ["pr_number", "auto_loop", "extra_prompt"],
        }
    )
    expected_concurrency_prefixes: dict[str, str] = field(
        default_factory=lambda: {
            "ai-dispatch.yml": "ai-dispatch-",
            "ai-fix.yml": "ai-fix-",
            "ai-review.yml": "ai-review-",
        }
    )
    required_markers: list[str] = field(default_factory=lambda: ["ai-pr-meta", "ai-review-context"])


@dataclass(frozen=True)
class ChatopsConfig:
    command_prefix: str = "ace"
    allowed_associations: list[str] = field(default_factory=lambda: ["OWNER", "MEMBER", "COLLABORATOR"])


@dataclass(frozen=True)
class AceConfig:
    tech_stack: TechStackConfig
    bot: BotConfig
    branch: BranchConfig
    labels: dict[str, LabelInfo]
    review: ReviewConfig
    ci_paths: CiPathsConfig
    error_recovery: ErrorRecoveryConfig
    workflow_validation: WorkflowValidationConfig
    chatops: ChatopsConfig


def _default_labels() -> dict[str, LabelInfo]:
    return {
        "triaging": LabelInfo(color="1D76DB", description="Ace is triaging this issue"),
        "confirmed": LabelInfo(color="0E8A16", description="Ace confirmed this is a real bug"),
        "not-a-bug": LabelInfo(color="B60205", description="Ace thinks this is not a bug"),
        "needs-human": LabelInfo(color="FBCA04", description="Ace needs human input or failed to proceed"),
        "fixing": LabelInfo(color="5319E7", description="Ace is preparing a fix"),
        "pr-opened": LabelInfo(color="0052CC", description="Ace opened a PR for this issue"),
        "managed": LabelInfo(color="5319E7", description="PR is managed by Ace loop"),
        "reviewing": LabelInfo(color="1D76DB", description="Ace is reviewing the PR"),
        "changes-requested": LabelInfo(color="D93F0B", description="Ace review requested changes"),
        "review-approved": LabelInfo(color="0E8A16", description="Ace review approved the PR"),
        "loop-exceeded": LabelInfo(color="B60205", description="Ace review/fix loop exceeded max rounds"),
    }


def _default_config() -> AceConfig:
    return AceConfig(
        tech_stack=TechStackConfig(),
        bot=BotConfig(),
        branch=BranchConfig(),
        labels=_default_labels(),
        review=ReviewConfig(),
        ci_paths=CiPathsConfig(),
        error_recovery=ErrorRecoveryConfig(),
        workflow_validation=WorkflowValidationConfig(),
        chatops=ChatopsConfig(),
    )


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _as_int(value: Any, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _as_str_list(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return list(default)


def _load_raw_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Malformed JSON in {path}: top-level value must be an object")
    return data


def load_ace_config(config_path: str | None = None) -> AceConfig:
    resolved_path = Path(config_path or os.getenv("ACE_CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    defaults = _default_config()

    if not resolved_path.exists():
        return defaults

    raw = _load_raw_config(path=resolved_path)

    if "tech_stack" not in raw:
        raise ValueError(f"tech_stack is required in {resolved_path}")

    known_keys = {
        "tech_stack",
        "bot",
        "branch",
        "labels",
        "review",
        "ci_paths",
        "error_recovery",
        "workflow_validation",
        "chatops",
    }
    unknown_keys = sorted(set(raw) - known_keys)
    if unknown_keys:
        logging.warning("Unknown ace config fields in %s: %s", resolved_path, ", ".join(unknown_keys))

    tech_stack_raw = _ensure_dict(raw.get("tech_stack"))
    bot_raw = _ensure_dict(raw.get("bot"))
    branch_raw = _ensure_dict(raw.get("branch"))
    labels_raw = _ensure_dict(raw.get("labels"))
    review_raw = _ensure_dict(raw.get("review"))
    ci_paths_raw = _ensure_dict(raw.get("ci_paths"))
    error_recovery_raw = _ensure_dict(raw.get("error_recovery"))
    workflow_validation_raw = _ensure_dict(raw.get("workflow_validation"))
    chatops_raw = _ensure_dict(raw.get("chatops"))

    merged_labels = dict(defaults.labels)
    for label_name, label_value in labels_raw.items():
        if not isinstance(label_name, str):
            continue
        label_dict = _ensure_dict(label_value)
        existing = merged_labels.get(label_name)
        merged_labels[label_name] = LabelInfo(
            color=_as_str(label_dict.get("color"), existing.color if existing else ""),
            description=_as_str(label_dict.get("description"), existing.description if existing else ""),
        )

    default_required_inputs = dict(defaults.workflow_validation.required_inputs)
    required_inputs_raw = _ensure_dict(workflow_validation_raw.get("required_inputs"))
    for workflow, fields in required_inputs_raw.items():
        if isinstance(workflow, str):
            default_required_inputs[workflow] = _as_str_list(fields, [])

    default_concurrency = dict(defaults.workflow_validation.expected_concurrency_prefixes)
    expected_concurrency_raw = _ensure_dict(workflow_validation_raw.get("expected_concurrency_prefixes"))
    for workflow, prefix in expected_concurrency_raw.items():
        if isinstance(workflow, str) and isinstance(prefix, str):
            default_concurrency[workflow] = prefix

    return AceConfig(
        tech_stack=TechStackConfig(
            language=_as_str(tech_stack_raw.get("language"), defaults.tech_stack.language),
            package_manager=_as_str(tech_stack_raw.get("package_manager"), defaults.tech_stack.package_manager),
            test_command=_as_str(tech_stack_raw.get("test_command"), defaults.tech_stack.test_command),
            type_check_command=_as_str(
                tech_stack_raw.get("type_check_command"),
                defaults.tech_stack.type_check_command,
            ),
            runner=_as_str(tech_stack_raw.get("runner"), defaults.tech_stack.runner),
        ),
        bot=BotConfig(
            name=_as_str(bot_raw.get("name"), defaults.bot.name),
            email=_as_str(bot_raw.get("email"), defaults.bot.email),
        ),
        branch=BranchConfig(
            prefix=_as_str(branch_raw.get("prefix"), defaults.branch.prefix),
            detection_patterns=_as_str_list(branch_raw.get("detection_patterns"), defaults.branch.detection_patterns),
        ),
        labels=merged_labels,
        review=ReviewConfig(
            max_rounds=_as_int(review_raw.get("max_rounds"), defaults.review.max_rounds),
        ),
        ci_paths=CiPathsConfig(
            scripts=_as_str_list(ci_paths_raw.get("scripts"), defaults.ci_paths.scripts),
            actions=_as_str_list(ci_paths_raw.get("actions"), defaults.ci_paths.actions),
        ),
        error_recovery=ErrorRecoveryConfig(
            max_consecutive_failures=_as_int(
                error_recovery_raw.get("max_consecutive_failures"),
                defaults.error_recovery.max_consecutive_failures,
            ),
            auto_label_on_max_failures=_as_bool(
                error_recovery_raw.get("auto_label_on_max_failures"),
                defaults.error_recovery.auto_label_on_max_failures,
            ),
        ),
        workflow_validation=WorkflowValidationConfig(
            required_inputs=default_required_inputs,
            expected_concurrency_prefixes=default_concurrency,
            required_markers=_as_str_list(
                workflow_validation_raw.get("required_markers"),
                defaults.workflow_validation.required_markers,
            ),
        ),
        chatops=ChatopsConfig(
            command_prefix=_as_str(chatops_raw.get("command_prefix"), defaults.chatops.command_prefix),
            allowed_associations=_as_str_list(
                chatops_raw.get("allowed_associations"),
                defaults.chatops.allowed_associations,
            ),
        ),
    )


def get_environment_block(config: AceConfig) -> str:
    ts = config.tech_stack
    return (
        "Environment:\n"
        f"- {ts.language}, {ts.package_manager} package manager (run tests with: {ts.test_command})\n"
        f"- GitHub Actions {ts.runner} runner\n"
        "- jq, git, gh CLI available\n"
        "- Do NOT install additional tools"
    )


def get_branch_prefix(config: AceConfig) -> str:
    return config.branch.prefix


def get_detection_patterns(config: AceConfig) -> list[str]:
    return list(config.branch.detection_patterns)


def get_workflow_validation(config: AceConfig) -> WorkflowValidationConfig:
    return config.workflow_validation


def validate_branch_config(config: AceConfig) -> list[str]:
    warnings: list[str] = []
    prefix_first_segment = config.branch.prefix.split("/")[0]
    patterns = config.branch.detection_patterns
    if not any(pattern.startswith(prefix_first_segment) for pattern in patterns):
        warnings.append(
            f"Branch prefix '{config.branch.prefix}' starts with '{prefix_first_segment}' "
            f"but no detection pattern matches '{prefix_first_segment}/*'"
        )
    return warnings
