from __future__ import annotations

import sys
from pathlib import Path

from scripts.ci import build_review_summary


def _run_main(monkeypatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_review_summary.py", *args])
    build_review_summary.main()


def test_build_review_summary_approved_header(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"decision": "APPROVED", "summary": "Looks good"})
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "## ✅ Approved" in output.read_text(encoding="utf-8")


def test_build_review_summary_changes_requested_header(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"decision": "CHANGES_REQUESTED", "summary": "Need updates"})
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "## ⚠️ Changes Requested" in output.read_text(encoding="utf-8")


def test_build_review_summary_blocking_issue_severity_badges(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "blocking_issues": [
                {"title": "A", "severity": "high", "why": "x", "suggested_fix": "fix"},
                {"title": "B", "severity": "medium", "why": "y", "suggested_fix": "fix"},
                {"title": "C", "severity": "low", "why": "z", "suggested_fix": "fix"},
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "🔴" in text
    assert "🟡" in text
    assert "🔵" in text


def test_build_review_summary_long_suggested_fix_uses_details(monkeypatch, tmp_path: Path, write_json) -> None:
    long_fix = "x" * 200
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "blocking_issues": [
                {"title": "A", "severity": "high", "why": "x", "suggested_fix": long_fix},
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "<details>" in output.read_text(encoding="utf-8")


def test_build_review_summary_short_suggested_fix_inline(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "blocking_issues": [
                {"title": "A", "severity": "high", "why": "x", "suggested_fix": "small fix"},
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "**Suggested fix:** small fix" in output.read_text(encoding="utf-8")


def test_build_review_summary_non_blocking_suggestions_plain_strings(monkeypatch, tmp_path: Path, write_json) -> None:
    """Backward compatibility: plain string suggestions still render as bullet list."""
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "non_blocking_suggestions": ["add docs", "add test"],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "- add docs" in text
    assert "- add test" in text


def test_build_review_summary_non_blocking_structured_suggestion(monkeypatch, tmp_path: Path, write_json) -> None:
    """Structured suggestion objects render with file, severity badge, and description."""
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "non_blocking_suggestions": [
                {
                    "file": "scripts/ci/run_opencode.py",
                    "description": "Consider logging a warning for malformed JSON lines.",
                    "severity": "low",
                    "lines": [42, 45],
                },
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "🔵" in text
    assert "`scripts/ci/run_opencode.py`" in text
    assert "(L42, 45)" in text
    assert "Consider logging a warning" in text


def test_build_review_summary_non_blocking_structured_no_lines(monkeypatch, tmp_path: Path, write_json) -> None:
    """Structured suggestion without lines omits line reference."""
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "non_blocking_suggestions": [
                {
                    "file": "docs/todo.md",
                    "description": "Remove before merge.",
                    "severity": "low",
                    "lines": [],
                },
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "`docs/todo.md`" in text
    assert "(L" not in text
    assert "Remove before merge." in text


def test_build_review_summary_non_blocking_structured_severity_badges(monkeypatch, tmp_path: Path, write_json) -> None:
    """Each severity level maps to the correct emoji."""
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "non_blocking_suggestions": [
                {"file": "a.py", "description": "high sev", "severity": "high", "lines": []},
                {"file": "b.py", "description": "medium sev", "severity": "medium", "lines": []},
                {"file": "c.py", "description": "low sev", "severity": "low", "lines": []},
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "🔴" in text
    assert "🟡" in text
    assert "🔵" in text


def test_build_review_summary_non_blocking_mixed_string_and_dict(monkeypatch, tmp_path: Path, write_json) -> None:
    """Mixed list of plain strings and structured dicts renders both correctly."""
    review_file = write_json(
        "review.json",
        {
            "decision": "CHANGES_REQUESTED",
            "summary": "Need updates",
            "non_blocking_suggestions": [
                "plain string suggestion",
                {
                    "file": "x.py",
                    "description": "structured suggestion",
                    "severity": "medium",
                    "lines": [10],
                },
            ],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "- plain string suggestion" in text
    assert "🟡" in text
    assert "`x.py`" in text
    assert "(L10)" in text
    assert "structured suggestion" in text


def test_build_review_summary_recommended_checks_code_block(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json(
        "review.json",
        {"decision": "APPROVED", "summary": "ok", "recommended_checks": ["pytest -q", "uv run basedpyright"]},
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "```" in text
    assert "pytest -q" in text


def test_build_review_summary_omits_empty_sections(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json(
        "review.json",
        {
            "decision": "APPROVED",
            "summary": "ok",
            "blocking_issues": [],
            "non_blocking_suggestions": [],
            "recommended_checks": [],
        },
    )
    output = tmp_path / "review_summary.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    text = output.read_text(encoding="utf-8")
    assert "Blocking Issues" not in text
    assert "Non-blocking Suggestions" not in text
    assert "Recommended Checks" not in text
