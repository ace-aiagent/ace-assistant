from __future__ import annotations

import json
import sys

import pytest

from scripts.ci import extract_marker_comment


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["extract_marker_comment.py", *args])
    extract_marker_comment.main()


def test_extract_json_from_body_reads_json_in_html_comment_after_marker() -> None:
    body = """intro
<!-- ai-pr-meta -->

<!-- {"ok": true} -->
"""
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"ok": True}


def test_extract_json_from_body_reads_json_in_html_comment_code_format() -> None:
    body = """<!-- ai-pr-meta -->
<!-- {"k": "v"} -->
"""
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"k": "v"}


def test_extract_json_from_body_reads_complex_json_in_html_comment() -> None:
    body = """<!-- ai-pr-meta -->
<!-- {"a": 1, "b": 2} -->
"""
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"a": 1, "b": 2}


def test_extract_json_from_body_handles_multiline_json_in_html_comment() -> None:
    body = """<!-- ai-pr-meta -->
<!-- {"x": 42, "y": [1, 2]} -->
"""
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"x": 42, "y": [1, 2]}


def test_extract_json_from_body_uses_content_after_specified_marker_only() -> None:
    body = """<!-- other -->
<!-- {"bad": true} -->
<!-- ai-pr-meta -->
<!-- {"good": true} -->
"""
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"good": True}


def test_extract_json_from_body_raises_when_marker_missing() -> None:
    with pytest.raises(ValueError, match="marker not found"):
        extract_marker_comment.extract_json_from_body("hello", "ai-pr-meta")


def test_extract_json_from_body_raises_when_marker_is_inline_text() -> None:
    body = "prefix <!-- ai-pr-meta --> suffix\n<!-- {\"ok\": true} -->"
    with pytest.raises(ValueError, match="marker not found"):
        extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")


def test_extract_json_from_body_accepts_indented_marker_line() -> None:
    body = "  <!--   ai-pr-meta   -->\n<!--   {\"ok\": true}   -->\n"
    result = extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")
    assert result == {"ok": True}


def test_extract_json_from_body_raises_when_no_json_payload_exists() -> None:
    body = """<!-- ai-pr-meta -->
not json here
still not json
"""
    with pytest.raises(ValueError, match="no json payload"):
        extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")


def test_extract_json_from_body_raises_on_malformed_json_in_html_comment() -> None:
    body = """<!-- ai-pr-meta -->
<!-- {"also": } -->
"""
    with pytest.raises(ValueError, match="no json payload"):
        extract_marker_comment.extract_json_from_body(body, "ai-pr-meta")


def test_extract_json_from_body_raises_for_empty_body() -> None:
    with pytest.raises(ValueError, match="marker not found"):
        extract_marker_comment.extract_json_from_body("", "ai-pr-meta")


def test_main_field_id_returns_comment_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    comments_file = write_json("comments.json", [{"id": 123, "body": "<!-- ai-pr-meta -->\n<!-- {} -->"}])
    _run_main(
        monkeypatch,
        ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "id"],
    )
    assert capsys.readouterr().out.strip() == "123"


def test_main_field_json_returns_parsed_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    comments_file = write_json(
        "comments.json",
        [{"id": 1, "body": "<!-- ai-pr-meta -->\n<!-- {\"foo\": \"bar\"} -->"}],
    )
    _run_main(
        monkeypatch,
        ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "json"],
    )
    assert json.loads(capsys.readouterr().out) == {"foo": "bar"}


def test_main_field_body_returns_comment_body(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    body = "<!-- ai-pr-meta -->\n<!-- {} -->"
    comments_file = write_json("comments.json", [{"id": 1, "body": body}])
    _run_main(
        monkeypatch,
        ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "body"],
    )
    assert capsys.readouterr().out.strip() == body


@pytest.mark.parametrize("field", ["id", "body", "json"])
def test_main_no_matching_comment_raises_system_exit(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
    write_json,
) -> None:
    comments_file = write_json("comments.json", [{"id": 1, "body": "nothing"}])
    with pytest.raises(SystemExit) as exc_info:
        _run_main(monkeypatch, ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", field])
    assert exc_info.value.code == 1


def test_main_multiple_comments_returns_last_matching_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    write_json,
) -> None:
    comments_file = write_json(
        "comments.json",
        [
            {"id": 1, "body": "<!-- ai-pr-meta -->\n<!-- {\"v\": 1} -->"},
            {"id": 2, "body": "<!-- ai-pr-meta -->\n<!-- {\"v\": 2} -->"},
        ],
    )
    _run_main(
        monkeypatch,
        ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "id"],
    )
    assert capsys.readouterr().out.strip() == "2"


def test_main_ignores_inline_marker_text_and_raises_system_exit(
    monkeypatch: pytest.MonkeyPatch,
    write_json,
) -> None:
    comments_file = write_json(
        "comments.json",
        [{"id": 1, "body": "contains <!-- ai-pr-meta --> inline only"}],
    )
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "id"],
        )
    assert exc_info.value.code == 1


def test_main_field_json_raises_system_exit_when_json_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    write_json,
) -> None:
    comments_file = write_json("comments.json", [{"id": 1, "body": "<!-- ai-pr-meta -->\n<!-- {broken} -->"}])
    with pytest.raises(SystemExit) as exc_info:
        _run_main(
            monkeypatch,
            ["--comments-file", str(comments_file), "--marker", "ai-pr-meta", "--field", "json"],
        )
    assert exc_info.value.code == 1


def test_main_missing_required_args_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["extract_marker_comment.py"])
    with pytest.raises(SystemExit):
        extract_marker_comment.main()
