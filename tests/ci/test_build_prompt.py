from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.ci import build_prompt


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_prompt.py", *args])
    build_prompt.main()


def test_build_prompt_triage_writes_output_and_expected_sections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "triage_prompt.md"

    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", REPO_NAME="org/repo", EXTRA_PROMPT="Follow this")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "triage",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "Repository: org/repo" in text
    assert "Issue number: 12" in text
    assert "Base branch: main" in text
    assert "Follow this" in text


def test_build_prompt_triage_omits_extra_prompt_when_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "triage_prompt.md"

    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", REPO_NAME="org/repo", EXTRA_PROMPT="")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "triage",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--output",
            str(output),
        ],
    )

    assert "Additional user instructions:" not in output.read_text(encoding="utf-8")


def test_build_prompt_fix_issue_writes_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    triage_file = write_json("triage.json", {"verdict": "CONFIRMED_BUG"})
    output = tmp_path / "fix_prompt.md"

    set_ci_env(
        ISSUE_NUMBER="12",
        BASE_BRANCH="main",
        FIX_BRANCH="ace/fix/issue-12-bug-r1",
        REPO_NAME="org/repo",
        EXTRA_PROMPT="",
    )
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--triage-file",
            str(triage_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "Source issue: #12" in text
    assert "Working branch: ace/fix/issue-12-bug-r1" in text


def test_build_prompt_fix_retry_loop_writes_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    review_file = write_json("review.json", {"decision": "CHANGES_REQUESTED"})
    output = tmp_path / "fix_loop_prompt.md"

    set_ci_env(PR_NUMBER="9", NEXT_ROUND="2", REPO_NAME="org/repo", EXTRA_PROMPT="")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--review-context-file",
            str(review_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "PR number: 9" in text
    assert "Current retry round: 2" in text


def test_build_prompt_review_writes_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    output = tmp_path / "review_prompt.md"

    set_ci_env(PR_NUMBER="9", REPO_NAME="org/repo", EXTRA_PROMPT="")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "review",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "You are a strict pull request reviewer." in text
    assert "PR number: 9" in text


def test_build_prompt_raises_when_required_file_args_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "triage_prompt.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_prompt.py",
            "--mode",
            "triage",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit):
        build_prompt.main()


def test_build_prompt_raises_for_missing_input_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, set_ci_env) -> None:
    output = tmp_path / "triage_prompt.md"
    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", REPO_NAME="org/repo")
    with pytest.raises(FileNotFoundError):
        _run_main(
            monkeypatch,
            [
                "--mode",
                "triage",
                "--issue-file",
                str(tmp_path / "missing_issue.json"),
                "--fields-file",
                str(tmp_path / "missing_fields.json"),
                "--output",
                str(output),
            ],
        )


def test_build_prompt_keeps_json_schema_braces_literal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "triage_prompt.md"

    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", REPO_NAME="org/repo")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "triage",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert '"verdict": "CONFIRMED_BUG | NOT_A_BUG | NEEDS_HUMAN"' in text
    assert '{' in text and '}' in text


_REQUIRED_SECTIONS = [
    "Environment:",
    "uv package manager",
    "AI_RESULT_BEGIN",
    "AI_RESULT_END",
    "CRITICAL",
]

_CI_PREAMBLE_MARKERS = [
    "CI/headless mode",
    "Do NOT ask for confirmation",
    "AI_RESULT_BEGIN",
]

_DEFAULT_ENVIRONMENT_BLOCK = (
    "Environment:\n"
    "          - Python 3.12, uv package manager (run tests with: uv run pytest)\n"
    "          - GitHub Actions ubuntu-latest runner\n"
    "          - jq, git, gh CLI available\n"
    "          - Do NOT install additional tools"
)


def _assert_prompt_has_required_sections(text: str) -> None:
    for section in _REQUIRED_SECTIONS:
        assert section in text, f"prompt 缺少必要段落: {section!r}"


def _assert_prompt_has_sandwich_pattern(text: str) -> None:
    for marker in _CI_PREAMBLE_MARKERS:
        assert marker in text, f"prompt 缺少 preamble 段落: {marker!r}"
    first_marker_pos = text.index("AI_RESULT_BEGIN")
    last_marker_pos = text.rindex("AI_RESULT_BEGIN")
    assert first_marker_pos < last_marker_pos, "AI_RESULT_BEGIN 应在 prompt 开头和结尾各出现一次（sandwich pattern）"


def test_triage_prompt_contains_environment_and_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--output", str(output)])

    _assert_prompt_has_required_sections(output.read_text(encoding="utf-8"))


def test_triage_prompt_default_environment_block_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--output", str(output)])

    text = output.read_text(encoding="utf-8")
    assert _DEFAULT_ENVIRONMENT_BLOCK in text


def test_triage_prompt_supports_custom_config_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    config_file = write_json(
        "ace-config.json",
        {
            "tech_stack": {
                "language": "Node.js 22",
                "package_manager": "npm",
                "test_command": "npm test",
                "type_check_command": "npm run typecheck",
                "runner": "ubuntu-24.04",
            }
        },
    )
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "triage",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--config-path",
            str(config_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert "- Node.js 22, npm package manager (run tests with: npm test)" in text
    assert "- GitHub Actions ubuntu-24.04 runner" in text
    assert "uv package manager" not in text


def test_fix_prompt_issue_contains_environment_and_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    triage_file = write_json("triage.json", {"verdict": "CONFIRMED_BUG"})
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="fix-1", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "fix", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--triage-file", str(triage_file), "--output", str(output)])

    _assert_prompt_has_required_sections(output.read_text(encoding="utf-8"))


def test_fix_retry_prompt_contains_environment_and_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    review_file = write_json("review.json", {"decision": "CHANGES_REQUESTED"})
    output = tmp_path / "prompt.md"

    set_ci_env(PR_NUMBER="1", NEXT_ROUND="2", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "fix", "--pr-file", str(pr_file), "--pr-meta-file", str(meta_file), "--review-context-file", str(review_file), "--output", str(output)])

    _assert_prompt_has_required_sections(output.read_text(encoding="utf-8"))


def test_triage_prompt_has_sandwich_pattern(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--output", str(output)])

    _assert_prompt_has_sandwich_pattern(output.read_text(encoding="utf-8"))


def test_fix_prompt_issue_has_sandwich_pattern(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    triage_file = write_json("triage.json", {"verdict": "CONFIRMED_BUG"})
    output = tmp_path / "prompt.md"

    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", FIX_BRANCH="fix-1", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "fix", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--triage-file", str(triage_file), "--output", str(output)])

    _assert_prompt_has_sandwich_pattern(output.read_text(encoding="utf-8"))


def test_fix_retry_prompt_has_sandwich_pattern(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    review_file = write_json("review.json", {"decision": "CHANGES_REQUESTED"})
    output = tmp_path / "prompt.md"

    set_ci_env(PR_NUMBER="1", NEXT_ROUND="2", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "fix", "--pr-file", str(pr_file), "--pr-meta-file", str(meta_file), "--review-context-file", str(review_file), "--output", str(output)])

    _assert_prompt_has_sandwich_pattern(output.read_text(encoding="utf-8"))


def test_review_prompt_has_sandwich_pattern(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    output = tmp_path / "prompt.md"

    set_ci_env(PR_NUMBER="1", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "review", "--pr-file", str(pr_file), "--pr-meta-file", str(meta_file), "--output", str(output)])

    _assert_prompt_has_sandwich_pattern(output.read_text(encoding="utf-8"))


def test_review_prompt_has_structured_non_blocking_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    output = tmp_path / "prompt.md"

    set_ci_env(PR_NUMBER="1", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "review", "--pr-file", str(pr_file), "--pr-meta-file", str(meta_file), "--output", str(output)])

    text = output.read_text(encoding="utf-8")
    assert '"file":' in text
    assert '"description":' in text
    assert '"severity":' in text
    assert '"lines":' in text


def test_triage_prompt_legacy_mode_has_marker_sandwich(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "prompt.md"

    monkeypatch.delenv("ACE_RESULT_PROTOCOL_MODE", raising=False)
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--output", str(output)])

    text = output.read_text(encoding="utf-8")
    assert "AI_RESULT_BEGIN" in text
    assert "AI_RESULT_END" in text


def test_triage_prompt_envelope_mode_has_envelope_instruction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "t", "body": "b"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "prompt.md"

    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "dual-read")
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(issue_file), "--fields-file", str(fields_file), "--output", str(output)])

    text = output.read_text(encoding="utf-8")
    assert "result-envelope.v1" in text
    assert "AI_RESULT_BEGIN" not in text


def test_fix_prompt_envelope_mode_has_mode_string(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    triage_file = write_json("triage.json", {"verdict": "CONFIRMED_BUG"})
    output = tmp_path / "fix_prompt.md"

    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "strict-envelope")
    set_ci_env(
        ISSUE_NUMBER="12",
        BASE_BRANCH="main",
        FIX_BRANCH="ace/fix/issue-12-bug-r1",
        REPO_NAME="org/repo",
    )
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--triage-file",
            str(triage_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert '"mode": "fix"' in text
    assert "result-envelope.v1" in text


def test_review_prompt_envelope_mode_has_mode_string(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    output = tmp_path / "review_prompt.md"

    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "dual-read")
    set_ci_env(PR_NUMBER="9", REPO_NAME="org/repo", EXTRA_PROMPT="")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "review",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert '"mode": "review"' in text
    assert "result-envelope.v1" in text


def test_retry_fix_prompt_uses_governed_review_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    oversize_summary = "x" * 12000
    checks = [f"check-{i:03d}" for i in range(200)]
    review_ctx = {
        "decision": "CHANGES_REQUESTED",
        "summary": oversize_summary,
        "blocking_issues": [{"title": "t", "severity": "high", "why": "w", "suggested_fix": "s"}],
        "recommended_checks": checks,
    }
    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1, "notes": "n" * 5000})
    review_file = write_json("review.json", review_ctx)
    output = tmp_path / "fix_loop_prompt.md"

    set_ci_env(PR_NUMBER="9", NEXT_ROUND="2", REPO_NAME="org/repo", EXTRA_PROMPT="p" * 3000)
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--review-context-file",
            str(review_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    start = text.index("Latest AI review JSON:")
    end = text.index("Required JSON schema:")
    injected_review_section = text[start:end]
    raw_review_section = build_prompt.json.dumps(review_ctx, ensure_ascii=False, indent=2)
    assert len(injected_review_section.encode("utf-8")) < len(raw_review_section.encode("utf-8"))


def test_fix_loop_prompt_does_not_contain_full_review_json_when_oversized(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    checks = [f"cmd-{i:03d}" for i in range(300)]
    review_ctx = {
        "decision": "CHANGES_REQUESTED",
        "summary": "summary",
        "blocking_issues": [{"title": "t", "severity": "high", "why": "w" * 1000, "suggested_fix": "s" * 1000}],
        "recommended_checks": checks,
    }
    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    review_file = write_json("review.json", review_ctx)
    output = tmp_path / "fix_loop_prompt.md"

    set_ci_env(PR_NUMBER="9", NEXT_ROUND="2", REPO_NAME="org/repo", EXTRA_PROMPT="")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--review-context-file",
            str(review_file),
            "--output",
            str(output),
        ],
    )

    text = output.read_text(encoding="utf-8")
    assert checks[0] in text
    assert checks[-1] not in text


def test_all_modes_legacy_still_emit_marker_preamble(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "legacy")

    triage_issue = write_json("triage_issue.json", {"title": "t", "body": "b"})
    triage_fields = write_json("triage_fields.json", {"base_branch": "main"})
    triage_output = tmp_path / "triage_prompt.md"
    set_ci_env(ISSUE_NUMBER="1", BASE_BRANCH="main", REPO_NAME="o/r")
    _run_main(monkeypatch, ["--mode", "triage", "--issue-file", str(triage_issue), "--fields-file", str(triage_fields), "--output", str(triage_output)])

    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    triage_file = write_json("triage.json", {"verdict": "CONFIRMED_BUG"})
    fix_output = tmp_path / "fix_prompt.md"
    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", FIX_BRANCH="ace/fix/issue-12-bug-r1", REPO_NAME="org/repo")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "fix",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--triage-file",
            str(triage_file),
            "--output",
            str(fix_output),
        ],
    )

    pr_file = write_json("pr.json", {"title": "PR", "body": "Body", "base": {"ref": "main"}, "head": {"ref": "fix"}})
    meta_file = write_json("meta.json", {"fix_round": 1})
    review_output = tmp_path / "review_prompt.md"
    set_ci_env(PR_NUMBER="9", REPO_NAME="org/repo")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "review",
            "--pr-file",
            str(pr_file),
            "--pr-meta-file",
            str(meta_file),
            "--output",
            str(review_output),
        ],
    )

    for text in (
        triage_output.read_text(encoding="utf-8"),
        fix_output.read_text(encoding="utf-8"),
        review_output.read_text(encoding="utf-8"),
    ):
        assert "AI_RESULT_BEGIN" in text
        assert "AI_RESULT_END" in text


def test_protocol_mode_raises_for_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "banana")
    with pytest.raises(ValueError, match="Unknown ACE_RESULT_PROTOCOL_MODE"):
        build_prompt._protocol_mode()


def test_build_prompt_writes_trim_meta_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    write_json,
    set_ci_env,
) -> None:
    import json

    issue_file = write_json("issue.json", {"title": "Bug title", "body": "Bug body"})
    fields_file = write_json("fields.json", {"base_branch": "main"})
    output = tmp_path / "triage_prompt.md"

    set_ci_env(ISSUE_NUMBER="12", BASE_BRANCH="main", REPO_NAME="org/repo")
    _run_main(
        monkeypatch,
        [
            "--mode",
            "triage",
            "--issue-file",
            str(issue_file),
            "--fields-file",
            str(fields_file),
            "--output",
            str(output),
        ],
    )

    trim_meta_path = Path(str(output) + ".trim_meta.json")
    assert trim_meta_path.exists(), ".trim_meta.json sidecar must be written next to output"
    trim_meta = json.loads(trim_meta_path.read_text(encoding="utf-8"))
    assert "context_trimmed" in trim_meta
    assert "trim_report" in trim_meta
    assert isinstance(trim_meta["context_trimmed"], bool)
    assert isinstance(trim_meta["trim_report"], dict)
