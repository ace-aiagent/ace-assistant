#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.ci._config import get_environment_block, load_ace_config
from scripts.ci._io_utils import read_json
from scripts.ci.prompt_governor import GoverningResult, govern
from scripts.ci.result_protocol import PROTOCOL_VERSION


_CI_OUTPUT_PREAMBLE = """IMPORTANT: You are running in CI/headless mode. Do NOT ask for confirmation or clarification.
You MUST output your final result as valid JSON between AI_RESULT_BEGIN and AI_RESULT_END markers.
No other output format is accepted. Proceed autonomously and produce the markers at the end.
"""

_CI_OUTPUT_EPILOGUE = """CRITICAL: You MUST return ONLY valid JSON between the markers below.
          Do NOT wrap JSON in markdown code blocks.
          Do NOT include any text outside the markers.
          Do NOT ask for user confirmation. Output the markers immediately after analysis.

          Return format:
          AI_RESULT_BEGIN
          <json>
          AI_RESULT_END
          """

_ENVELOPE_OUTPUT_PREAMBLE = """IMPORTANT: You are running in CI/headless mode. Do NOT ask for confirmation or clarification.
You MUST output your final result as a single compact result-envelope.v1 JSON object.
No other output format is accepted. Proceed autonomously.
"""

_ENVELOPE_OUTPUT_EPILOGUE = f"""CRITICAL: Output ONLY one compact JSON object conforming to {PROTOCOL_VERSION}.
          Do NOT wrap JSON in markdown code blocks.
          Do NOT include any text outside the JSON object.
          Do NOT ask for user confirmation. Output the envelope immediately after analysis.

          Required envelope structure:
          {{
            "protocol_version": "{PROTOCOL_VERSION}",
            "mode": "<MODE>",
            "status": "ok",
            "result": {{ <mode-specific fields here> }},
            "diagnostics": null
          }}
          """


def _protocol_mode() -> str:
    mode = os.environ.get("ACE_RESULT_PROTOCOL_MODE", "legacy").strip().lower()
    valid = {"legacy", "dual-read", "strict-envelope"}
    if mode not in valid:
        raise ValueError(f"Unknown ACE_RESULT_PROTOCOL_MODE: {mode!r}. Valid: {sorted(valid)}")
    return mode


def _output_preamble() -> str:
    if _protocol_mode() in {"dual-read", "strict-envelope"}:
        return _ENVELOPE_OUTPUT_PREAMBLE
    return _CI_OUTPUT_PREAMBLE


def _output_epilogue(mode: str) -> str:
    if _protocol_mode() in {"dual-read", "strict-envelope"}:
        return _ENVELOPE_OUTPUT_EPILOGUE.replace("<MODE>", mode)
    return _CI_OUTPUT_EPILOGUE


def _build_history_section(pr_meta: dict[str, Any]) -> str:
    review_history = pr_meta.get("review_history", [])
    fix_history = pr_meta.get("fix_history", [])

    if not review_history and not fix_history:
        return ""

    lines = ["\n### Previous Rounds Summary"]

    for review in review_history[-3:]:
        round_num = review.get("round", "?")
        decision = review.get("decision", "UNKNOWN")
        summary = review.get("summary", "")[:80]
        blocking = review.get("blocking_count", 0)
        lines.append(f"- Review#{round_num}: {decision} - {summary}... ({blocking} blocking issues)")

    for fix in fix_history[-3:]:
        round_num = fix.get("round", "?")
        summary = fix.get("summary", "")[:80]
        files = fix.get("changed_files", "")[:50]
        lines.append(f"- Fix#{round_num}: {summary}... [files: {files}]")

    return "\n".join(lines) + "\n"


def _build_triage_prompt(
    *, issue: dict[str, Any], fields: dict[str, Any], config_path: str | None = None
) -> tuple[str, GoverningResult]:
    issue_number = os.environ["ISSUE_NUMBER"]
    base_branch = os.environ["BASE_BRANCH"]
    repo_name = os.environ["REPO_NAME"]
    extra_prompt = os.environ.get("EXTRA_PROMPT", "").strip()
    gov = govern(
        "triage",
        extra_prompt=extra_prompt,
        issue_body=issue.get("body") or "",
    )
    extra_prompt = gov.extra_prompt
    issue_body = gov.issue_body
    config = load_ace_config(config_path)
    environment_block = "\n          ".join(get_environment_block(config).splitlines())

    extra_section = ""
    if extra_prompt:
        extra_section = f"""

          Additional user instructions:
          {extra_prompt}
          """

    prompt = f"""{_output_preamble()}
          You are a strict bug triage agent working inside a Git repository.

          Repository: {repo_name}
          Issue number: {issue_number}
          Base branch: {base_branch}

          {environment_block}

          Current task:
          1. Read the issue carefully.
          2. Inspect the checked out repository.
          3. Decide whether this is a real bug that should enter auto-fix.
          4. Do NOT modify any files in this triage phase.
          {extra_section}
          Issue title:
          {issue.get("title", "")}

          Issue body:
          {issue_body}

          Parsed issue fields JSON:
          {json.dumps(fields, ensure_ascii=False, indent=2)}

          Rules:
          - Only return CONFIRMED_BUG if you have enough evidence from the issue plus repository inspection.
          - Return NOT_A_BUG if the report is clearly invalid, expected behavior, unsupported environment, or not reproducible from available evidence.
          - Return NEEDS_HUMAN if key information is missing or you cannot safely confirm the bug.
          - Be conservative. False positives are worse than saying NEEDS_HUMAN.
          - Return JSON only inside the markers below.

          Required JSON schema:
          {{
            "verdict": "CONFIRMED_BUG | NOT_A_BUG | NEEDS_HUMAN",
            "reason": "short explanation",
            "confidence": "low | medium | high",
            "suspected_files": ["optional/path1", "optional/path2"],
            "fix_strategy": "how you would fix it if confirmed",
            "verification_plan": ["step 1", "step 2"],
            "branch_slug": "short-english-slug-describing-the-bug (e.g. fix-login-crash, null-avatar-url). Use lowercase, hyphens only, max 48 chars. Translate non-English titles to English."
          }}

          {_output_epilogue("triage")}"""
    return prompt, gov


def _build_fix_prompt(
    *,
    issue: dict[str, Any],
    fields: dict[str, Any],
    triage: dict[str, Any],
    config_path: str | None = None,
) -> tuple[str, GoverningResult]:
    repo_name = os.environ["REPO_NAME"]
    issue_number = os.environ["ISSUE_NUMBER"]
    base_branch = os.environ["BASE_BRANCH"]
    fix_branch = os.environ["FIX_BRANCH"]
    extra_prompt = os.environ.get("EXTRA_PROMPT", "").strip()
    gov = govern(
        "issue-fix",
        extra_prompt=extra_prompt,
        issue_body=issue.get("body") or "",
    )
    extra_prompt = gov.extra_prompt
    issue_body = gov.issue_body
    config = load_ace_config(config_path)
    environment_block = "\n          ".join(get_environment_block(config).splitlines())

    extra_section = ""
    if extra_prompt:
        extra_section = f"""

          Additional user instructions:
          {extra_prompt}
          """

    prompt = f"""{_output_preamble()}
          You are an autonomous bug-fixing agent working in a Git repository.

          Repository: {repo_name}
          Source issue: #{issue_number}
          Base branch: {base_branch}
          Working branch: {fix_branch}

          {environment_block}

          Task:
          - Fix the confirmed bug described below.
          - Make the smallest correct change.
          - Update or add tests if needed.
          - Run focused verification commands when feasible.
          - Do not change unrelated code.
          - Do not create commits yourself. The workflow will commit for you.
          {extra_section}
          Issue title:
          {issue.get("title", "")}

          Issue body:
          {issue_body}

          Parsed issue fields JSON:
          {json.dumps(fields, ensure_ascii=False, indent=2)}

          Triage JSON:
          {json.dumps(triage, ensure_ascii=False, indent=2)}

          Required JSON schema:
          {{
            "summary": "what was changed",
            "changed_files": ["path1", "path2"],
            "verification": [
              {{"command": "cmd", "result": "pass | fail | not_run", "details": "one-line note, max 80 chars"}}
            ],
            "followups": ["optional item"]
          }}

          IMPORTANT: Keep the JSON compact. Each "details" value must be a short one-line note (<=80 chars), NOT full command output.

          {_output_epilogue("fix")}"""
    return prompt, gov


def _build_fix_loop_prompt(
    *,
    pr: dict[str, Any],
    pr_meta: dict[str, Any],
    review_ctx: dict[str, Any],
    config_path: str | None = None,
) -> tuple[str, GoverningResult]:
    repo_name = os.environ["REPO_NAME"]
    pr_number = os.environ["PR_NUMBER"]
    next_round = os.environ["NEXT_ROUND"]
    extra_prompt = os.environ.get("EXTRA_PROMPT", "").strip()
    gov = govern(
        "retry-fix",
        extra_prompt=extra_prompt,
        pr_body=pr.get("body") or "",
        pr_meta=pr_meta,
        review_context=review_ctx,
    )
    extra_prompt = gov.extra_prompt
    pr_body = gov.pr_body
    pr_meta_json = gov.pr_meta_json
    review_ctx_json = gov.review_context_json
    config = load_ace_config(config_path)
    environment_block = "\n          ".join(get_environment_block(config).splitlines())
    base_ref = (pr.get("base") or {}).get("ref", "")
    head_ref = (pr.get("head") or {}).get("ref", "")
    pr_title = pr.get("title", "")
    history_section = _build_history_section(pr_meta)

    extra_section = ""
    if extra_prompt:
        extra_section = f"""

          Additional user instructions:
          {extra_prompt}
          """

    prompt = f"""{_output_preamble()}
          You are an autonomous bug-fixing agent working on an existing pull request branch.

          Repository: {repo_name}
          PR number: {pr_number}
          Base ref: {base_ref}
          Head ref: {head_ref}
          Current retry round: {next_round}

          {environment_block}

          Task:
          - Read the previous AI review feedback below.
          - Fix only the blocking issues raised by that review.
          - Stay on the current branch.
          - Do not create commits yourself.
          - Keep the patch as small and targeted as possible.
          - Re-run focused verification when feasible.
          {extra_section}
          PR title:
          {pr_title}

          PR body:
          {pr_body}
          {history_section}
          AI PR meta JSON:
          {pr_meta_json}

          Latest AI review JSON:
          {review_ctx_json}

          Required JSON schema:
          {{
            "summary": "what was fixed in this retry round",
            "changed_files": ["path1", "path2"],
            "verification": [
              {{"command": "cmd", "result": "pass | fail | not_run", "details": "one-line note, max 80 chars"}}
            ],
            "remaining_risks": ["optional item"]
          }}

          IMPORTANT: Keep the JSON compact. Each "details" value must be a short one-line note (<=80 chars), NOT full command output.

          {_output_epilogue("fix")}"""
    return prompt, gov


def _build_review_prompt(
    *, pr: dict[str, Any], pr_meta: dict[str, Any], config_path: str | None = None
) -> tuple[str, GoverningResult]:
    repo_name = os.environ["REPO_NAME"]
    pr_number = os.environ["PR_NUMBER"]
    extra_prompt = os.environ.get("EXTRA_PROMPT", "").strip()
    gov = govern(
        "review",
        extra_prompt=extra_prompt,
        pr_body=pr.get("body") or "",
        pr_meta=pr_meta,
    )
    extra_prompt = gov.extra_prompt
    pr_body = gov.pr_body
    pr_meta_json = gov.pr_meta_json
    config = load_ace_config(config_path)
    environment_block = "\n          ".join(get_environment_block(config).splitlines())
    base_ref = (pr.get("base") or {}).get("ref", "")
    head_ref = (pr.get("head") or {}).get("ref", "")
    pr_title = pr.get("title", "")
    history_section = _build_history_section(pr_meta)

    extra_section = ""
    if extra_prompt:
        extra_section = f"""

          Additional user instructions:
          {extra_prompt}
          """

    prompt = f"""{_output_preamble()}
          You are a strict pull request reviewer.

          Repository: {repo_name}
          PR number: {pr_number}
          Base ref: {base_ref}
          Head ref: {head_ref}

          {environment_block}

          Task:
          - Review the current checked out PR branch against its base branch.
          - Focus on correctness, regressions, edge cases, missing tests, and maintainability.
          - Do NOT modify files.
          - Be strict on real problems, but do not nitpick style-only issues unless they create maintenance or correctness risk.
          - You MAY run read-only verification commands (e.g. uv run pytest, uv run basedpyright) to validate your findings.
          {extra_section}
          PR title:
          {pr_title}

          PR body:
          {pr_body}
          {history_section}
          AI PR meta JSON:
          {pr_meta_json}

          Required JSON schema:
          {{
            "decision": "APPROVED | CHANGES_REQUESTED",
            "summary": "short summary",
            "blocking_issues": [
              {{
                "title": "short title",
                "severity": "high | medium | low",
                "why": "why this blocks approval",
                "suggested_fix": "how to fix it"
              }}
            ],
            "non_blocking_suggestions": [
              {{
                "file": "path/to/file.py",
                "description": "what could be improved and why",
                "severity": "low",
                "lines": [10, 20]
              }}
            ],
            "recommended_checks": ["optional command or test"]
          }}

          {_output_epilogue("review")}"""
    return prompt, gov


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["triage", "fix", "review"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--issue-file")
    parser.add_argument("--fields-file")
    parser.add_argument("--triage-file")
    parser.add_argument("--pr-file")
    parser.add_argument("--pr-meta-file")
    parser.add_argument("--review-context-file")
    parser.add_argument("--config-path")
    args = parser.parse_args()

    mode = args.mode

    prompt = ""
    gov: GoverningResult | None = None

    if mode == "triage":
        if not args.issue_file or not args.fields_file:
            parser.error("triage mode requires --issue-file and --fields-file")
        prompt, gov = _build_triage_prompt(
            issue=read_json(args.issue_file),
            fields=read_json(args.fields_file),
            config_path=args.config_path,
        )

    elif mode == "fix":
        if args.review_context_file:
            if not args.pr_file or not args.pr_meta_file:
                parser.error(
                    "fix retry mode requires --pr-file --pr-meta-file --review-context-file"
                )
            prompt, gov = _build_fix_loop_prompt(
                pr=read_json(args.pr_file),
                pr_meta=read_json(args.pr_meta_file),
                review_ctx=read_json(args.review_context_file),
                config_path=args.config_path,
            )
        else:
            if not args.issue_file or not args.fields_file or not args.triage_file:
                parser.error("fix mode requires --issue-file --fields-file --triage-file")
            prompt, gov = _build_fix_prompt(
                issue=read_json(args.issue_file),
                fields=read_json(args.fields_file),
                triage=read_json(args.triage_file),
                config_path=args.config_path,
            )

    elif mode == "review":
        if not args.pr_file or not args.pr_meta_file:
            parser.error("review mode requires --pr-file --pr-meta-file")
        prompt, gov = _build_review_prompt(
            pr=read_json(args.pr_file),
            pr_meta=read_json(args.pr_meta_file),
            config_path=args.config_path,
        )

    Path(args.output).write_text(prompt, encoding="utf-8")

    if gov is not None:
        trim_meta = {
            "context_trimmed": gov.total_input_bytes > gov.total_output_bytes,
            "trim_report": gov.trim_report,
        }
        Path(args.output + ".trim_meta.json").write_text(
            json.dumps(trim_meta, ensure_ascii=False), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
