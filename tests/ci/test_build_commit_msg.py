from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.ci import build_commit_msg


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_commit_msg.py", *args])
    build_commit_msg.main()


def test_build_commit_message_initial_mode_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json(
        "fix_result.json",
        {
            "summary": "fix race condition",
            "changed_files": ["a.py", "b.py"],
            "verification": [{"command": "pytest", "result": "pass", "details": "ok"}],
        },
    )
    output = tmp_path / "commit_message.txt"
    set_ci_env(ISSUE_NUMBER="99", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-99-race-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "fix(issue #99):" in text
    assert "Source issue: #99" in text
    assert "Changed files:" in text
    assert "Verification:" in text


def test_build_commit_message_retry_mode_format(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json("fix_loop_result.json", {"summary": "retry fix", "changed_files": ["x.py"], "verification": []})
    output = tmp_path / "commit_message.txt"
    set_ci_env(PR_NUMBER="12", ROUND="2", HEAD_REF="ace/fix/issue-12-x-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "retry",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "fix(pr #12, round 2):" in text
    assert "Target PR: #12" in text
    assert "Retry round: 2" in text


def test_build_commit_message_uses_fallback_for_empty_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json("result.json", {"summary": "", "changed_files": [], "verification": []})
    output = tmp_path / "commit_message.txt"
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-1-bug-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )
    assert "resolve reported bug" in output.read_text(encoding="utf-8")


def test_build_commit_message_truncates_subject_at_180(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json("result.json", {"summary": "x" * 400, "changed_files": [], "verification": []})
    output = tmp_path / "commit_message.txt"
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-1-bug-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )
    subject = output.read_text(encoding="utf-8").splitlines()[0]
    assert len(subject) <= 180


def test_build_commit_message_uses_changed_files_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json("result.json", {"summary": "done", "changed_files": [], "verification": [{"command": "x", "result": "pass", "details": "ok"}]})
    output = tmp_path / "commit_message.txt"
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-1-bug-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )
    assert "No changed files" in output.read_text(encoding="utf-8")


def test_build_commit_message_uses_verification_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    result_file = write_json("result.json", {"summary": "done", "changed_files": ["a.py"], "verification": []})
    output = tmp_path / "commit_message.txt"
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-1-bug-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(result_file),
            "--output",
            str(output),
        ],
    )
    assert "No verification" in output.read_text(encoding="utf-8")


def test_build_commit_message_is_multiline_for_both_modes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    initial_file = write_json("initial.json", {"summary": "s", "changed_files": ["a.py"], "verification": []})
    retry_file = write_json("retry.json", {"summary": "s", "changed_files": ["a.py"], "verification": []})
    initial_output = tmp_path / "initial.txt"
    retry_output = tmp_path / "retry.txt"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-1-bug-r1")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "initial",
            "--result-file",
            str(initial_file),
            "--output",
            str(initial_output),
        ],
    )
    set_ci_env(PR_NUMBER="2", ROUND="3", HEAD_REF="branch")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "retry",
            "--result-file",
            str(retry_file),
            "--output",
            str(retry_output),
        ],
    )

    assert len(initial_output.read_text(encoding="utf-8").splitlines()) > 3
    assert len(retry_output.read_text(encoding="utf-8").splitlines()) > 3
