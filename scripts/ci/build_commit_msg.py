#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json


def _build_initial_commit_message(data: dict[str, Any]) -> str:
    issue_number = os.environ["ISSUE_NUMBER"]
    base_branch = os.environ["BASE_BRANCH"]
    fix_branch = os.environ["FIX_BRANCH"]

    summary = (data.get("summary") or "").strip()
    if not summary:
        summary = "resolve reported bug"

    summary = " ".join(summary.split())
    subject = f"fix(issue #{issue_number}): {summary}"
    subject = subject[:180]

    lines = [
        subject,
        "",
        f"Source issue: #{issue_number}",
        f"Base branch: {base_branch}",
        f"Working branch: {fix_branch}",
        "",
        "What changed:",
        data.get("summary") or "No summary provided.",
        "",
        "Changed files:",
    ]

    changed_files = data.get("changed_files") or []
    if changed_files:
        lines.extend([f"- {item}" for item in changed_files])
    else:
        lines.append("- No changed files reported by agent")

    lines.extend(["", "Verification:"])
    verification = data.get("verification") or []
    if verification:
        for item in verification:
            cmd = item.get("command", "")
            result = item.get("result", "")
            details = item.get("details", "")
            lines.append(f"- {cmd}: {result} ({details})")
    else:
        lines.append("- No verification reported by agent")

    return "\n".join(lines) + "\n"


def _build_retry_commit_message(data: dict[str, Any]) -> str:
    pr_number = os.environ["PR_NUMBER"]
    round_value = os.environ.get("ROUND") or ""
    head_ref = os.environ.get("HEAD_REF") or ""

    summary = (data.get("summary") or "")
    summary = " ".join(summary.split())
    if not summary:
        summary = "address AI review feedback"

    subject = f"fix(pr #{pr_number}, round {round_value}): {summary}"
    subject = subject[:180]

    lines = [
        subject,
        "",
        f"Target PR: #{pr_number}",
        f"Retry round: {round_value}",
        f"Branch: {head_ref}",
        "",
        "What changed:",
        data.get("summary") or "No summary provided.",
        "",
        "Changed files:",
    ]

    changed_files = data.get("changed_files") or []
    for item in changed_files:
        lines.append(f"- {item}")

    lines.extend(["", "Verification:"])
    verification = data.get("verification") or []
    for item in verification:
        lines.append(
            f"- {item.get('command', '')}: {item.get('result', '')} ({item.get('details', '')})"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["initial", "retry"], required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = read_json(args.result_file)

    if args.mode == "initial":
        message = _build_initial_commit_message(data)
    else:
        message = _build_retry_commit_message(data)

    Path(args.output).write_text(message, encoding="utf-8")


if __name__ == "__main__":
    main()
