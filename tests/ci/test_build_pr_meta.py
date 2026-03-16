from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.ci import build_pr_meta


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_pr_meta.py", *args])
    build_pr_meta.main()


def test_build_pr_meta_initial_sets_default_rounds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    set_ci_env,
) -> None:
    output = tmp_path / "pr_meta_comment.md"
    set_ci_env(ISSUE_NUMBER="20", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-20-a-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--output",
            str(output),
        ],
    )
    text = output.read_text(encoding="utf-8")
    assert "`1` / `3`" in text


def test_build_pr_meta_update_handles_null_source_issue_as_na(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
) -> None:
    meta_file = write_json(
        "pr_meta_new.json",
        {
            "source_issue": None,
            "base_branch": "main",
            "branch": "ace/fix/issue-20-a-r1",
            "fix_round": 2,
            "max_rounds": 3,
            "status": "reviewing",
            "active_operation": "idle",
            "requested_head_sha": "",
            "last_reviewed_head_sha": "",
            "auto_loop": True,
        },
    )
    output = tmp_path / "pr_meta_comment.md"
    _run_main(
        monkeypatch,
        [
            "--mode",
            "update",
            "--input-file",
            str(meta_file),
            "--output",
            str(output),
        ],
    )
    assert "Source issue: N/A" in output.read_text(encoding="utf-8")


def test_build_pr_meta_update_fills_missing_optional_fields_for_legacy_meta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
) -> None:
    meta_file = write_json(
        "legacy_pr_meta.json",
        {
            "source_issue": 20,
            "base_branch": "main",
            "branch": "ace/fix/issue-20-a-r1",
            "fix_round": 1,
            "max_rounds": 3,
            "status": "reviewing",
        },
    )
    output = tmp_path / "pr_meta_comment.md"
    _run_main(
        monkeypatch,
        [
            "--mode",
            "update",
            "--input-file",
            str(meta_file),
            "--output",
            str(output),
        ],
    )
    text = output.read_text(encoding="utf-8")
    assert "- Active operation: `idle`" in text
    assert "- Auto loop: `True`" in text


def test_build_pr_meta_contains_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    set_ci_env,
) -> None:
    output = tmp_path / "pr_meta_comment.md"
    set_ci_env(ISSUE_NUMBER="20", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-20-a-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--output",
            str(output),
        ],
    )
    assert "<!-- ai-pr-meta -->" in output.read_text(encoding="utf-8")


def test_build_pr_meta_contains_embedded_json_html_comment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    set_ci_env,
) -> None:
    output = tmp_path / "pr_meta_comment.md"
    set_ci_env(ISSUE_NUMBER="20", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-20-a-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--output",
            str(output),
        ],
    )
    text = output.read_text(encoding="utf-8")
    assert "<!-- {" in text and "} -->" in text


def test_build_pr_meta_initial_with_custom_max_rounds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    set_ci_env,
    write_json,
) -> None:
    config_file = write_json(
        "custom_config.json",
        {
            "tech_stack": {
                "language": "Python 3.12",
                "package_manager": "uv",
                "test_command": "uv run pytest",
                "type_check_command": "uv run basedpyright --level error",
                "runner": "ubuntu-latest",
            },
            "review": {"max_rounds": 5},
        },
    )
    output = tmp_path / "pr_meta_comment.md"
    set_ci_env(ISSUE_NUMBER="20", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-20-a-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--output",
            str(output),
            "--config-path",
            str(config_file),
        ],
    )
    text = output.read_text(encoding="utf-8")
    assert "`1` / `5`" in text


def test_build_pr_meta_initial_contains_error_recovery_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    set_ci_env,
) -> None:
    output = tmp_path / "pr_meta_comment.md"
    set_ci_env(ISSUE_NUMBER="20", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-20-a-r1")
    _run_main(monkeypatch, ["--mode", "initial", "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert '"failure_count": 0' in text or '"failure_count":0' in text
    assert '"last_error": null' in text or '"last_error":null' in text
