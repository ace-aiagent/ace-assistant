#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload: dict[str, Any] = read_json(args.result_file)
    decision = str(payload.get("decision") or "UNKNOWN")
    body = (
        "<!-- ai-review-context -->\n"
        + f"Review context metadata (decision: {decision}).\n"
        + "<!-- "
        + json.dumps(payload, ensure_ascii=False)
        + " -->"
    )
    Path(args.output).write_text(body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
