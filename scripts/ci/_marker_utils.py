#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from typing import Any


def _find_marker_line_end(body: str, marker: str) -> int:
    pattern = re.compile(
        rf"^[ \t]*<!--\s*{re.escape(marker)}\s*-->[ \t]*\r?$",
        flags=re.MULTILINE,
    )
    match = pattern.search(body)
    if not match:
        return -1
    return match.end()


def _contains_marker_line(body: str, marker: str) -> bool:
    return _find_marker_line_end(body=body, marker=marker) >= 0


def extract_json_from_body(body: str, marker: str) -> Any:
    marker_end = _find_marker_line_end(body=body, marker=marker)
    if marker_end < 0:
        raise ValueError("marker not found")

    tail = body[marker_end:].strip()

    for block in re.findall(r"<!--\s*(.*?)\s*-->", tail, flags=re.DOTALL):
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue

    raise ValueError("no json payload found after marker")
