#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re

from scripts.ci._config import get_branch_prefix, load_ace_config
from scripts.ci._io_utils import read_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-file", required=True)
    parser.add_argument("--triage-file", required=True)
    parser.add_argument("--config-path", required=False, default=None)
    args = parser.parse_args()

    issue = read_json(args.issue_file)
    triage = read_json(args.triage_file)

    issue_number = issue["number"]

    # Prefer branch_slug from triage AI (already English)
    text = (triage.get("branch_slug") or "").strip()

    # Normalize: lowercase, hyphens only, max 48 chars
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    text = text[:48].strip("-") or "bug"

    config = load_ace_config(config_path=args.config_path)
    prefix = get_branch_prefix(config)

    print(f"fix_branch={prefix}-{issue_number}-{text}-r1")


if __name__ == "__main__":
    main()
