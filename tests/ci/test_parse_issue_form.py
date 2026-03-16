from __future__ import annotations

import json
import sys

import pytest

from scripts.ci import parse_issue_form


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["parse_issue_form.py", *args])
    parse_issue_form.main()


def test_slugify_normal_text_to_lowercase_with_underscores() -> None:
    assert parse_issue_form.slugify("Base Branch Name") == "base_branch_name"


def test_slugify_replaces_special_characters_with_underscore() -> None:
    assert parse_issue_form.slugify("A@B/C.D") == "a_b_c_d"


def test_slugify_strips_leading_and_trailing_special_characters() -> None:
    assert parse_issue_form.slugify("---Hello---") == "hello"


def test_slugify_keeps_already_slugified_value() -> None:
    assert parse_issue_form.slugify("already_slugified") == "already_slugified"


def test_slugify_empty_string_returns_empty() -> None:
    assert parse_issue_form.slugify("") == ""


def test_parse_markdown_sections_parses_standard_multiple_sections() -> None:
    body = """### Base branch
main

### Summary
something broke
"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result == {"base_branch": "main", "summary": "something broke"}


def test_parse_markdown_sections_parses_single_section() -> None:
    body = """### Summary
only one section
"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result == {"summary": "only one section"}


def test_parse_markdown_sections_keeps_empty_content_under_heading() -> None:
    body = """### Summary

"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result == {"summary": ""}


def test_parse_markdown_sections_returns_empty_dict_without_headings() -> None:
    result = parse_issue_form.parse_markdown_sections("no section markers here")
    assert result == {}


def test_parse_markdown_sections_slugifies_heading_with_special_characters() -> None:
    body = """### Environment / OS (Version)
macOS 14
"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result == {"environment_os_version": "macOS 14"}


def test_parse_markdown_sections_handles_consecutive_headings_without_content() -> None:
    body = """### First
### Second
value
"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result == {"first": "", "second": "value"}


def test_parse_markdown_sections_preserves_markdown_formatting() -> None:
    body = """### Summary
**bold** and `code` and - list
"""
    result = parse_issue_form.parse_markdown_sections(body)
    assert result["summary"] == "**bold** and `code` and - list"


def test_main_reads_issue_file_and_writes_json_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    write_json,
) -> None:
    issue_file = write_json(
        "issue.json",
        {"body": "### Base branch\nmain\n\n### Summary\nbroken"},
    )
    output = tmp_path / "issue_fields.json"

    _run_main(monkeypatch, ["--issue-file", str(issue_file), "--output", str(output)])

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "base_branch": "main",
        "summary": "broken",
    }


def test_main_writes_empty_dict_when_issue_body_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    write_json,
) -> None:
    issue_file = write_json("issue.json", {"title": "x"})
    output = tmp_path / "issue_fields.json"

    _run_main(monkeypatch, ["--issue-file", str(issue_file), "--output", str(output)])

    assert json.loads(output.read_text(encoding="utf-8")) == {}


def test_main_missing_required_args_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["parse_issue_form.py"])
    with pytest.raises(SystemExit):
        parse_issue_form.main()
