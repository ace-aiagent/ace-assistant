#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json


SUMMARY_LIMIT_BYTES = 400
BLOCKING_ISSUE_LIMIT = 5
BLOCKING_ISSUE_TITLE_LIMIT_BYTES = 120
BLOCKING_ISSUE_WHY_LIMIT_BYTES = 300
BLOCKING_ISSUE_SUGGESTED_FIX_LIMIT_BYTES = 300
RECOMMENDED_CHECK_LIMIT = 3
RECOMMENDED_CHECK_LIMIT_BYTES = 120
HTML_COMMENT_END = "-->"
HTML_COMMENT_SAFE_END = "--\\>"


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    truncated = encoded[:max_bytes]
    while True:
        try:
            return truncated.decode("utf-8") + "..."
        except UnicodeDecodeError:
            truncated = truncated[:-1]


def _compact_issue(issue: Any) -> dict[str, Any]:
    if not isinstance(issue, dict):
        return {
            "title": "",
            "severity": None,
            "why": "",
            "suggested_fix": "",
        }

    return {
        "title": _truncate_utf8(str(issue.get("title") or ""), BLOCKING_ISSUE_TITLE_LIMIT_BYTES),
        "severity": issue.get("severity"),
        "why": _truncate_utf8(str(issue.get("why") or ""), BLOCKING_ISSUE_WHY_LIMIT_BYTES),
        "suggested_fix": _truncate_utf8(
            str(issue.get("suggested_fix") or ""), BLOCKING_ISSUE_SUGGESTED_FIX_LIMIT_BYTES
        ),
    }


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_blocking_issues = payload.get("blocking_issues")
    raw_recommended_checks = payload.get("recommended_checks")

    blocking_issues = raw_blocking_issues if isinstance(raw_blocking_issues, list) else []
    recommended_checks = raw_recommended_checks if isinstance(raw_recommended_checks, list) else []

    return {
        "decision": str(payload.get("decision") or "UNKNOWN"),
        "summary": _truncate_utf8(str(payload.get("summary") or ""), SUMMARY_LIMIT_BYTES),
        "blocking_issues": [_compact_issue(issue) for issue in blocking_issues[:BLOCKING_ISSUE_LIMIT]],
        "recommended_checks": [
            _truncate_utf8(str(check or ""), RECOMMENDED_CHECK_LIMIT_BYTES)
            for check in recommended_checks[:RECOMMENDED_CHECK_LIMIT]
        ],
    }


def _dump_comment_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False).replace(HTML_COMMENT_END, HTML_COMMENT_SAFE_END)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload: dict[str, Any] = read_json(args.result_file)
    compact_payload = _compact_payload(payload)
    decision = compact_payload["decision"]
    body = (
        "<!-- ace-review-context -->\n"
        + f"Review context metadata (decision: {decision}).\n"
        + "<!-- "
        + _dump_comment_json(compact_payload)
        + " -->"
    )
    Path(args.output).write_text(body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
