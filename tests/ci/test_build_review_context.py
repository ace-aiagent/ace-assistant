from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.ci import build_review_context


def _run_main(monkeypatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["build_review_context.py", *args])
    build_review_context.main()


def test_build_review_context_contains_marker(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"decision": "APPROVED"})
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])
    assert "<!-- ace-review-context -->" in output.read_text(encoding="utf-8")


def test_build_review_context_contains_json_dump(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {"decision": "CHANGES_REQUESTED", "summary": "x"}
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    text = output.read_text(encoding="utf-8")
    assert f"<!-- {json.dumps(payload, ensure_ascii=False)} -->" in text


def test_build_review_context_hides_json_payload_from_visible_body(monkeypatch, tmp_path: Path, write_json) -> None:
    payload = {"decision": "APPROVED", "summary": "ok"}
    review_file = write_json("review.json", payload)
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "<!-- ace-review-context -->"
    assert lines[1] == "Review context metadata (decision: APPROVED)."
    assert lines[2].startswith("<!-- ") and lines[2].endswith(" -->")


def test_build_review_context_uses_unknown_when_decision_missing(monkeypatch, tmp_path: Path, write_json) -> None:
    review_file = write_json("review.json", {"summary": "missing decision"})
    output = tmp_path / "review_context_comment.md"
    _run_main(monkeypatch, ["--result-file", str(review_file), "--output", str(output)])

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "Review context metadata (decision: UNKNOWN)."
