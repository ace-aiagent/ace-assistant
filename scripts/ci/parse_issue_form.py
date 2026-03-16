#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re

from scripts.ci._io_utils import read_json, write_json


def slugify(label: str) -> str:
    label = label.strip().lower()
    label = re.sub(r"[^a-z0-9]+", "_", label)
    return label.strip("_")


def parse_markdown_sections(body: str) -> dict[str, str]:
    """
    Parse GitHub issue form rendered markdown.

    Example:
    ### Base branch
    main

    ### Summary
    something broke
    """
    pattern = re.compile(
        r"^###\s+(?P<title>.+?)\n(?P<content>.*?)(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    result: dict[str, str] = {}

    for match in pattern.finditer(body):
        title = match.group("title").strip()
        content = match.group("content").strip()
        result[slugify(title)] = content

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    issue = read_json(args.issue_file)
    body = issue.get("body") or ""

    parsed = parse_markdown_sections(body)

    write_json(args.output, parsed, indent=2)


if __name__ == "__main__":
    main()
