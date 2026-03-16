from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.ci import build_pr_content


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_pr_content.py", *args])
    build_pr_content.main()


def test_build_pr_content_title_strips_bug_prefix_and_includes_issue_number(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "[bug]: login crash", "body": "desc"})
    fix_result_file = write_json("fix_result.json", {"summary": "fixed", "verification": []})
    title_out = tmp_path / "pr_title.txt"
    body_out = tmp_path / "pr_body.md"

    set_ci_env(ISSUE_NUMBER="18", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-18-login-crash-r1")
    _run_main(
        monkeypatch,
        [
            "--issue-file",
            str(issue_file),
            "--result-file",
            str(fix_result_file),
            "--title-output",
            str(title_out),
            "--body-output",
            str(body_out),
        ],
    )
    assert title_out.read_text(encoding="utf-8").strip() == "fix(issue #18): login crash"


def test_build_pr_content_body_includes_required_sections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "bug", "body": "desc"})
    fix_result_file = write_json(
        "fix_result.json",
        {
            "summary": "updated null checks",
            "verification": [{"command": "pytest", "result": "pass", "details": "ok"}],
        },
    )
    title_out = tmp_path / "pr_title.txt"
    body_out = tmp_path / "pr_body.md"

    set_ci_env(ISSUE_NUMBER="18", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-18-login-crash-r1")
    _run_main(
        monkeypatch,
        [
            "--issue-file",
            str(issue_file),
            "--result-file",
            str(fix_result_file),
            "--title-output",
            str(title_out),
            "--body-output",
            str(body_out),
        ],
    )
    text = body_out.read_text(encoding="utf-8")
    assert "Closes #18" in text
    assert "`main`" in text
    assert "`ace/fix/issue-18-login-crash-r1`" in text
    assert "updated null checks" in text
    assert "pytest" in text


def test_build_pr_content_empty_title_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "", "body": "desc"})
    fix_result_file = write_json("fix_result.json", {"summary": "fixed", "verification": []})
    title_out = tmp_path / "pr_title.txt"
    body_out = tmp_path / "pr_body.md"

    set_ci_env(ISSUE_NUMBER="18", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-18-login-crash-r1")
    _run_main(
        monkeypatch,
        [
            "--issue-file",
            str(issue_file),
            "--result-file",
            str(fix_result_file),
            "--title-output",
            str(title_out),
            "--body-output",
            str(body_out),
        ],
    )
    assert "bug fix" in title_out.read_text(encoding="utf-8")


def test_build_pr_content_empty_verification_uses_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "bug", "body": "desc"})
    fix_result_file = write_json("fix_result.json", {"summary": "fixed", "verification": []})
    title_out = tmp_path / "pr_title.txt"
    body_out = tmp_path / "pr_body.md"

    set_ci_env(ISSUE_NUMBER="18", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-18-login-crash-r1")
    _run_main(
        monkeypatch,
        [
            "--issue-file",
            str(issue_file),
            "--result-file",
            str(fix_result_file),
            "--title-output",
            str(title_out),
            "--body-output",
            str(body_out),
        ],
    )
    assert "No verification" in body_out.read_text(encoding="utf-8")
