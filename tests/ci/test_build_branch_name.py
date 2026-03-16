from __future__ import annotations

import sys

import pytest

from scripts.ci import build_branch_name


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
) -> str:
    monkeypatch.setattr(sys, "argv", ["build_branch_name.py", *args])
    build_branch_name.main()
    return capsys.readouterr().out.strip()


def test_build_branch_name_normal_slug(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], write_json) -> None:
    issue_file = write_json("issue.json", {"number": 12})
    triage_file = write_json("triage.json", {"branch_slug": "fix-login-crash"})
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file)],
    )
    assert out == "fix_branch=ace/fix/issue-12-fix-login-crash-r1"


def test_build_branch_name_normalizes_special_characters(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"number": 12})
    triage_file = write_json("triage.json", {"branch_slug": "Fix@@Login Crash!!!"})
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file)],
    )
    assert out == "fix_branch=ace/fix/issue-12-fix-login-crash-r1"


def test_build_branch_name_truncates_slug_to_48_chars(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"number": 12})
    triage_file = write_json("triage.json", {"branch_slug": "a" * 80})
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file)],
    )
    assert out == f"fix_branch=ace/fix/issue-12-{'a' * 48}-r1"


def test_build_branch_name_uses_bug_when_slug_empty(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"number": 12})
    triage_file = write_json("triage.json", {"branch_slug": ""})
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file)],
    )
    assert out == "fix_branch=ace/fix/issue-12-bug-r1"


def test_build_branch_name_uses_translated_english_slug(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"number": 35})
    triage_file = write_json("triage.json", {"branch_slug": "null-avatar-url"})
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file)],
    )
    assert out == "fix_branch=ace/fix/issue-35-null-avatar-url-r1"


def test_build_branch_name_with_custom_prefix(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"number": 42})
    triage_file = write_json("triage.json", {"branch_slug": "custom-fix"})
    config_file = write_json(
        "config.json",
        {
            "tech_stack": {"language": "Python 3.12", "package_manager": "uv", "test_command": "uv run pytest", "type_check_command": "uv run basedpyright --level error", "runner": "ubuntu-latest"},
            "branch": {"prefix": "bot/bugfix"},
        },
    )
    out = _run_main(
        monkeypatch,
        capsys,
        ["--issue-file", str(issue_file), "--triage-file", str(triage_file), "--config-path", str(config_file)],
    )
    assert out == "fix_branch=bot/bugfix-42-custom-fix-r1"
