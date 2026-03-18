from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.ci import build_review_context


def _run_main(monkeypatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_review_context.py", *args])
    build_review_context.main()


def _read_output_lines(output: Path) -> list[str]:
    return output.read_text(encoding="utf-8").splitlines()


def _load_hidden_payload(output: Path) -> dict[str, Any]:
    lines = _read_output_lines(output)
    assert lines[2].startswith("<!-- ") and lines[2].endswith(" -->")
    hidden_json = lines[2][5:-4].replace("--\\>", "-->")
    return json.loads(hidden_json)


def test_build_review_context_contains_marker(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"decision": "APPROVED"})
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "<!-- ace-review-context -->" in output.read_text(encoding="utf-8")


def test_build_review_context_hides_json_payload_from_visible_body(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {"decision": "APPROVED", "summary": "ok"}
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    lines = _read_output_lines(output)
    assert lines[0] == "<!-- ace-review-context -->"
    assert lines[1] == "Review context metadata (decision: APPROVED)."
    assert lines[2].startswith("<!-- ") and lines[2].endswith(" -->")
    assert lines[1] == "Review context metadata (decision: APPROVED)."
    assert _load_hidden_payload(output) == {
        "decision": "APPROVED",
        "summary": "ok",
        "blocking_issues": [],
        "recommended_checks": [],
    }


def test_build_review_context_uses_unknown_when_decision_missing(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"summary": "missing decision"})
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    lines = _read_output_lines(output)
    assert lines[1] == "Review context metadata (decision: UNKNOWN)."


def test_compact_fields_only(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {
        "decision": "CHANGES_REQUESTED",
        "summary": "Need targeted fixes.",
        "blocking_issues": [
            {
                "title": "Missing retry guard",
                "severity": "high",
                "why": "Retries can loop forever.",
                "suggested_fix": "Stop after the configured retry cap.",
                "extra": "drop me",
            }
        ],
        "recommended_checks": ["python -m pytest tests/ci -q"],
        "non_blocking_suggestions": ["not persisted"],
        "confidence": 0.42,
    }
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    assert _load_hidden_payload(output) == {
        "decision": "CHANGES_REQUESTED",
        "summary": "Need targeted fixes.",
        "blocking_issues": [
            {
                "title": "Missing retry guard",
                "severity": "high",
                "why": "Retries can loop forever.",
                "suggested_fix": "Stop after the configured retry cap.",
            }
        ],
        "recommended_checks": ["python -m pytest tests/ci -q"],
    }


def test_summary_truncated(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {"decision": "APPROVED", "summary": "a" * 401}
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    assert _load_hidden_payload(output)["summary"] == ("a" * 400) + "..."


def test_blocking_issues_capped_at_5(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {
        "decision": "CHANGES_REQUESTED",
        "blocking_issues": [
            {
                "title": f"Issue {index}",
                "severity": "medium",
                "why": f"Why {index}",
                "suggested_fix": f"Fix {index}",
            }
            for index in range(6)
        ],
    }
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    hidden_payload = _load_hidden_payload(output)
    assert len(hidden_payload["blocking_issues"]) == 5
    assert hidden_payload["blocking_issues"][-1]["title"] == "Issue 4"


def test_recommended_checks_capped_at_3(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {
        "decision": "APPROVED",
        "recommended_checks": ["check-1", "check-2", "check-3", "check-4"],
    }
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    assert _load_hidden_payload(output)["recommended_checks"] == ["check-1", "check-2", "check-3"]


def test_html_comment_safe_escaping(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {
        "decision": "CHANGES_REQUESTED",
        "summary": "Keep parser safe --> no broken comment",
    }
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    lines = _read_output_lines(output)
    assert "--\\>" in lines[2]
    assert _load_hidden_payload(output)["summary"] == "Keep parser safe --> no broken comment"


def test_unicode_stability(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {
        "decision": "CHANGES_REQUESTED",
        "summary": "需要修复登录🔒路径",
        "blocking_issues": [
            {
                "title": "编码保持稳定",
                "severity": "high",
                "why": "中文与 emoji 需要完整保留。",
                "suggested_fix": "继续使用 ensure_ascii=False。",
            }
        ],
        "recommended_checks": ["pytest -q", "运行中文回归"],
    }
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"

    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    assert _load_hidden_payload(output) == payload
