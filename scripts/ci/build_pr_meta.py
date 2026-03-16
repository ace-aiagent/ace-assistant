#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.ci._config import load_ace_config
from scripts.ci._io_utils import read_json


def _build_initial_payload(auto_loop: bool = True, config_path: str | None = None) -> dict[str, Any]:
    config = load_ace_config(config_path=config_path)
    return {
        "source_issue": int(os.environ["ISSUE_NUMBER"]),
        "base_branch": os.environ["BASE_BRANCH"],
        "branch": os.environ["FIX_BRANCH"],
        "fix_round": 1,
        "max_rounds": config.review.max_rounds,
        "status": "reviewing",
        "active_operation": "idle",
        "requested_head_sha": "",
        "last_reviewed_head_sha": "",
        "auto_loop": auto_loop,
        "last_error": None,
        "failure_count": 0,
    }


def _render_initial(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    lines = [
        "<!-- ai-pr-meta -->",
        f"<!-- {payload_json} -->",
        "**Ace PR Metadata**",
        "",
        f"- Source issue: #{payload['source_issue']}",
        f"- Base branch: `{payload['base_branch']}`",
        f"- Managed branch: `{payload['branch']}`",
        f"- Fix round: `{payload['fix_round']}` / `{payload['max_rounds']}`",
        f"- Status: `{payload['status']}`",
        f"- Active operation: `{payload['active_operation']}`",
        f"- Auto loop: `{payload['auto_loop']}`",
    ]
    return "\n".join(lines) + "\n"


def _render_update(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    source_issue = payload.get("source_issue")
    source_issue_text = f"#{source_issue}" if source_issue is not None else "N/A"

    lines = [
        "<!-- ai-pr-meta -->",
        f"<!-- {payload_json} -->",
        "**Ace PR Metadata**",
        "",
        f"- Source issue: {source_issue_text}",
        f"- Base branch: `{payload.get('base_branch')}`",
        f"- Managed branch: `{payload.get('branch')}`",
        f"- Fix round: `{payload.get('fix_round')}` / `{payload.get('max_rounds')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Active operation: `{payload['active_operation']}`",
        f"- Auto loop: `{payload['auto_loop']}`",
    ]

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["initial", "update"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--input-file")
    parser.add_argument("--active-operation")
    parser.add_argument("--requested-head-sha")
    parser.add_argument("--last-reviewed-head-sha")
    parser.add_argument("--auto-loop", default="true")
    parser.add_argument("--config-path", required=False, default=None)
    args = parser.parse_args()

    if args.mode == "initial":
        auto_loop = args.auto_loop.lower() == "true"
        body = _render_initial(_build_initial_payload(auto_loop=auto_loop, config_path=args.config_path))
    else:
        if not args.input_file:
            parser.error("update mode requires --input-file")
        payload = read_json(args.input_file)
        payload.setdefault("active_operation", "idle")
        payload.setdefault("requested_head_sha", "")
        payload.setdefault("last_reviewed_head_sha", "")
        payload.setdefault("auto_loop", True)

        if args.active_operation is not None:
            payload["active_operation"] = args.active_operation
        if args.requested_head_sha is not None:
            payload["requested_head_sha"] = args.requested_head_sha
        if args.last_reviewed_head_sha is not None:
            payload["last_reviewed_head_sha"] = args.last_reviewed_head_sha
        if "--auto-loop" in sys.argv:
            payload["auto_loop"] = args.auto_loop.lower() == "true"

        body = _render_update(payload)

    Path(args.output).write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
