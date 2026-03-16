#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json
from scripts.ci._marker_utils import _contains_marker_line, extract_json_from_body


def _find_comment_id(*, comments: list[dict[str, Any]], marker: str) -> str:
    for item in reversed(comments):
        body = item.get("body") or ""
        if not _contains_marker_line(body=body, marker=marker):
            continue
        return str(item.get("id", ""))
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments-file", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue-number", required=True)
    args = parser.parse_args()

    comments: list[dict[str, Any]] = read_json(args.comments_file)
    comment_id = _find_comment_id(comments=comments, marker=args.marker)
    body = Path(args.body_file).read_text(encoding="utf-8")

    if comment_id:
        subprocess.run(
            [
                "gh",
                "api",
                f"repos/{args.repo}/issues/comments/{comment_id}",
                "-X",
                "PATCH",
                "-f",
                f"body={body}",
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "gh",
                "api",
                f"repos/{args.repo}/issues/{args.issue_number}/comments",
                "-X",
                "POST",
                "-f",
                f"body={body}",
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
