#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys

from scripts.ci._io_utils import read_json
from scripts.ci._marker_utils import _contains_marker_line, _find_marker_line_end, extract_json_from_body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comments-file", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--field", choices=["id", "json", "body"], required=True)
    args = parser.parse_args()

    comments = read_json(args.comments_file)
    found = None
    for item in reversed(comments):
        body = item.get("body") or ""
        if _contains_marker_line(body=body, marker=args.marker):
            found = item
            break

    if found is None:
        print("Error: marker not found", file=sys.stderr)
        sys.exit(1)

    if args.field == "id":
        print(found.get("id", ""))
        return

    if args.field == "body":
        print(found.get("body", ""))
        return

    if args.field == "json":
        try:
            data = extract_json_from_body(found.get("body") or "", args.marker)
        except Exception:
            print("Error: JSON extraction failed", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
