from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.ci._marker_utils import (
    _contains_marker_line,
    _find_marker_line_end,
    extract_json_from_body,
)


class Test_find_marker_line_end:
    """Tests for _find_marker_line_end function."""

    @pytest.mark.parametrize(
        ("body", "marker", "expected"),
        [
            pytest.param(
                "<!-- test-marker -->\n",
                "test-marker",
                20,
                id="marker_found_returns_position_after",
            ),
            pytest.param(
                "prefix\n<!-- test-marker -->\nsuffix",
                "test-marker",
                27,
                id="marker_with_prefix_and_suffix",
            ),
            pytest.param(
                "<!-- test-marker -->\n<!-- test-marker -->\n",
                "test-marker",
                20,
                id="multiple_occurrences_returns_first",
            ),
            pytest.param(
                "no marker here",
                "test-marker",
                -1,
                id="marker_not_found_returns_minus_one",
            ),
            pytest.param(
                "",
                "test-marker",
                -1,
                id="empty_body_returns_minus_one",
            ),
            pytest.param(
                "  <!--   test-marker   -->\n",
                "test-marker",
                26,
                id="indented_marker_with_spaces",
            ),
            pytest.param(
                "\t<!--\ttest-marker\t-->\t\n",
                "test-marker",
                22,
                id="marker_with_tabs",
            ),
            pytest.param(
                "line1\nline2\n<!-- test-marker -->\nline4",
                "test-marker",
                32,
                id="marker_on_third_line",
            ),
            pytest.param(
                "<!-- ai-pr-meta -->\n",
                "ai-pr-meta",
                19,
                id="ai_pr_meta_marker",
            ),
            pytest.param(
                "<!-- test-marker -->\r\n",
                "test-marker",
                21,
                id="marker_with_windows_line_ending",
            ),
        ],
    )
    def test_find_marker_line_end(self, body: str, marker: str, expected: int) -> None:
        assert _find_marker_line_end(body, marker) == expected


class Test_contains_marker_line:
    """Tests for _contains_marker_line function."""

    @pytest.mark.parametrize(
        ("body", "marker", "expected"),
        [
            pytest.param(
                "<!-- test-marker -->\n",
                "test-marker",
                True,
                id="marker_present_returns_true",
            ),
            pytest.param(
                "no marker here",
                "test-marker",
                False,
                id="marker_absent_returns_false",
            ),
            pytest.param(
                "prefix <!-- test-marker --> suffix\n",
                "test-marker",
                False,
                id="marker_inline_returns_false",
            ),
            pytest.param(
                "",
                "test-marker",
                False,
                id="empty_body_returns_false",
            ),
            pytest.param(
                "contains test-marker as substring",
                "test-marker",
                False,
                id="partial_marker_returns_false",
            ),
            pytest.param(
                "  <!--   test-marker   -->\n",
                "test-marker",
                True,
                id="indented_marker_returns_true",
            ),
            pytest.param(
                "<!-- ai-pr-meta -->\ndata",
                "ai-pr-meta",
                True,
                id="ai_pr_meta_marker_returns_true",
            ),
        ],
    )
    def test_contains_marker_line(self, body: str, marker: str, expected: bool) -> None:
        assert _contains_marker_line(body, marker) is expected


class Test_extract_json_from_body:
    """Tests for extract_json_from_body function."""

    @pytest.mark.parametrize(
        ("body", "marker", "expected"),
        [
            pytest.param(
                "<!-- test-marker -->\n<!-- {\"format\": \"html-comment\"} -->",
                "test-marker",
                {"format": "html-comment"},
                id="json_in_html_comment",
            ),
            pytest.param(
                "<!-- test-marker -->\n\n\n<!-- {\"after_empty_lines\": true} -->",
                "test-marker",
                {"after_empty_lines": True},
                id="json_in_html_comment_after_empty_lines",
            ),
            pytest.param(
                "<!-- first -->\n{\"bad\": true}\n<!-- test-marker -->\n<!-- {\"good\": true} -->",
                "test-marker",
                {"good": True},
                id="uses_content_after_specified_marker",
            ),
            pytest.param(
                "<!-- test-marker -->\n<!-- {\"a\": 1, \"b\": 2, \"c\": {\"d\": 3}} -->",
                "test-marker",
                {"a": 1, "b": 2, "c": {"d": 3}},
                id="complex_nested_structure_in_html_comment",
            ),
        ],
    )
    def test_extract_json_from_body_success(
        self, body: str, marker: str, expected: dict[str, Any]
    ) -> None:
        result = extract_json_from_body(body, marker)
        assert result == expected

    @pytest.mark.parametrize(
        ("body", "marker", "error_match"),
        [
            pytest.param(
                "no marker here",
                "test-marker",
                "marker not found",
                id="marker_not_found_raises",
            ),
            pytest.param(
                "prefix <!-- test-marker --> suffix\n{\"ok\": true}",
                "test-marker",
                "marker not found",
                id="inline_marker_raises",
            ),
            pytest.param(
                "",
                "test-marker",
                "marker not found",
                id="empty_body_raises",
            ),
            pytest.param(
                "<!-- test-marker -->\nnot json\nstill not json",
                "test-marker",
                "no json payload found after marker",
                id="no_valid_json_raises",
            ),
            pytest.param(
                "<!-- test-marker -->\n<!-- {\"broken\": } -->",
                "test-marker",
                "no json payload found after marker",
                id="malformed_html_comment_json_raises",
            ),
            pytest.param(
                "<!-- test-marker -->",
                "test-marker",
                "no json payload found after marker",
                id="marker_with_no_content_raises",
            ),
        ],
    )
    def test_extract_json_from_body_raises(
        self, body: str, marker: str, error_match: str
    ) -> None:
        with pytest.raises(ValueError, match=error_match):
            extract_json_from_body(body, marker)
