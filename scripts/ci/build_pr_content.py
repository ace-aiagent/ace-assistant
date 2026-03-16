#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--title-output", required=True)
    parser.add_argument("--body-output", required=True)
    args = parser.parse_args()

    issue = read_json(args.issue_file)
    fix_result: dict[str, Any] = read_json(args.result_file)

    issue_number = os.environ["ISSUE_NUMBER"]
    base_branch = os.environ["BASE_BRANCH"]
    fix_branch = os.environ["FIX_BRANCH"]

    title = (issue.get("title") or "").strip()
    title = re.sub(r"^\[bug\]\s*:?\s*", "", title, flags=re.I).strip()
    if not title:
        title = "bug fix"

    pr_title = f"fix(issue #{issue_number}): {title}"

    lines = [
        f"Closes #{issue_number}",
        "",
        "This PR was opened by the Ace bug-fix pipeline.",
        "",
        f"- Base branch: `{base_branch}`",
        f"- Managed branch: `{fix_branch}`",
        "- Initial fix round: `1`",
        "",
        "Fix summary:",
        fix_result.get("summary") or "No summary provided.",
        "",
        "Verification:",
    ]

    verification = fix_result.get("verification") or []
    if verification:
        for item in verification:
            lines.append(
                f"- {item.get('command', '')}: {item.get('result', '')} ({item.get('details', '')})"
            )
    else:
        lines.append("- No verification reported by agent")

    Path(args.title_output).write_text(pr_title + "\n", encoding="utf-8")
    Path(args.body_output).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
