#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


BUDGET_BYTES = {
    "triage": 12_288,
    "issue-fix": 14_336,
    "retry-fix": 10_240,
    "review": 12_288,
}

CAP_EXTRA_PROMPT_BYTES = 1_024
CAP_ISSUE_BODY_BYTES = 4_096
CAP_PR_BODY_BYTES = 4_096
CAP_PR_META_BYTES = 1_536
CAP_REVIEW_CONTEXT_BYTES = 3_072


@dataclass(eq=True)
class GoverningResult:
    extra_prompt: str
    issue_body: str
    pr_body: str
    pr_meta_json: str
    review_context_json: str
    trim_report: dict[str, Any]
    total_input_bytes: int
    total_output_bytes: int
    budget_bytes: int


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    truncated = encoded[:max_bytes]
    while True:
        try:
            return truncated.decode("utf-8") + "..."
        except UnicodeDecodeError:
            truncated = truncated[:-1]


def _json_compact(payload: dict[str, Any] | None) -> str:
    if payload is None:
        payload = {}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _len_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _stats(input_text: str, output_text: str) -> dict[str, int]:
    input_bytes = _len_bytes(input_text)
    output_bytes = _len_bytes(output_text)
    return {
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "trimmed_bytes": max(0, input_bytes - output_bytes),
    }


def _copy_json_like(payload: dict | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _trim_recommended_checks_for_cap(review_context: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    ctx = _copy_json_like(review_context)
    raw_checks = ctx.pop("recommended_checks", None)
    checks = raw_checks if isinstance(raw_checks, list) else []

    without_checks_json = _json_compact(ctx)
    if _len_bytes(without_checks_json) > max_bytes:
        return ctx

    while True:
        candidate = _copy_json_like(ctx)
        candidate["recommended_checks"] = checks
        if _len_bytes(_json_compact(candidate)) <= max_bytes:
            return candidate
        if not checks:
            return ctx
        checks = checks[:-1]


def _fit_review_context_json(ctx: dict[str, Any], max_bytes: int) -> str:
    compact = _json_compact(ctx)
    if _len_bytes(compact) <= max_bytes:
        return compact

    work = _copy_json_like(ctx)

    if isinstance(work.get("recommended_checks"), list):
        work["recommended_checks"] = []
    compact = _json_compact(work)
    if _len_bytes(compact) <= max_bytes:
        return compact

    if "summary" in work:
        work["summary"] = ""

    compact = _json_compact(work)
    if _len_bytes(compact) <= max_bytes:
        return compact

    blocking = work.get("blocking_issues")
    if isinstance(blocking, list):
        for issue in blocking:
            if isinstance(issue, dict):
                issue["why"] = ""
                issue["suggested_fix"] = ""

    compact = _json_compact(work)
    if _len_bytes(compact) <= max_bytes:
        return compact

    minimal = {
        "decision": work.get("decision"),
        "blocking_issues": work.get("blocking_issues", []),
    }
    compact = _json_compact(minimal)
    if _len_bytes(compact) <= max_bytes:
        return compact

    return compact


def _truncate_to_budget(text: str, reduce_bytes: int) -> str:
    if reduce_bytes <= 0:
        return text
    current = _len_bytes(text)
    target = max(0, current - reduce_bytes)
    if current <= target:
        return text
    if target <= 0:
        return ""
    candidate = _truncate_utf8(text, max(0, target - 3))
    while _len_bytes(candidate) > target:
        target -= 1
        if target <= 0:
            return ""
        candidate = _truncate_utf8(text, max(0, target - 3))
    return candidate


def govern(
    mode: str,
    *,
    extra_prompt: str = "",
    issue_body: str = "",
    pr_body: str = "",
    pr_meta: dict | None = None,
    review_context: dict | None = None,
) -> GoverningResult:
    if mode not in BUDGET_BYTES:
        raise ValueError(f"Unknown governor mode: {mode!r}. Valid: {sorted(BUDGET_BYTES)}")

    budget_bytes = BUDGET_BYTES[mode]

    in_pr_meta_json = _json_compact(pr_meta)
    in_review_context_obj = _copy_json_like(review_context)
    in_review_context_json = _json_compact(in_review_context_obj)

    governed_review_ctx = _trim_recommended_checks_for_cap(in_review_context_obj, CAP_REVIEW_CONTEXT_BYTES)

    out_extra_prompt = _truncate_utf8(extra_prompt, CAP_EXTRA_PROMPT_BYTES)

    out_pr_body = _truncate_utf8(pr_body, CAP_PR_BODY_BYTES)
    out_issue_body = _truncate_utf8(issue_body, CAP_ISSUE_BODY_BYTES)

    out_pr_meta_json = _truncate_utf8(in_pr_meta_json, CAP_PR_META_BYTES)

    out_review_context_json = _fit_review_context_json(governed_review_ctx, CAP_REVIEW_CONTEXT_BYTES)

    def _total_bytes() -> int:
        return (
            _len_bytes(out_extra_prompt)
            + _len_bytes(out_issue_body)
            + _len_bytes(out_pr_body)
            + _len_bytes(out_pr_meta_json)
            + _len_bytes(out_review_context_json)
        )

    total_output_bytes = _total_bytes()
    if total_output_bytes > budget_bytes:
        checks = governed_review_ctx.get("recommended_checks")
        if isinstance(checks, list):
            while checks and total_output_bytes > budget_bytes:
                checks = checks[:-1]
                governed_review_ctx["recommended_checks"] = checks
                out_review_context_json = _fit_review_context_json(governed_review_ctx, CAP_REVIEW_CONTEXT_BYTES)
                total_output_bytes = _total_bytes()

        if total_output_bytes > budget_bytes:
            out_extra_prompt = _truncate_to_budget(out_extra_prompt, total_output_bytes - budget_bytes)
            total_output_bytes = _total_bytes()

        if total_output_bytes > budget_bytes:
            out_pr_body = _truncate_to_budget(out_pr_body, total_output_bytes - budget_bytes)
            total_output_bytes = _total_bytes()
        if total_output_bytes > budget_bytes:
            out_issue_body = _truncate_to_budget(out_issue_body, total_output_bytes - budget_bytes)
            total_output_bytes = _total_bytes()

        if total_output_bytes > budget_bytes:
            out_pr_meta_json = _truncate_to_budget(out_pr_meta_json, total_output_bytes - budget_bytes)
            total_output_bytes = _total_bytes()

        if total_output_bytes > budget_bytes:
            out_review_context_json = _truncate_to_budget(
                out_review_context_json,
                total_output_bytes - budget_bytes,
            )
            total_output_bytes = _total_bytes()

    trim_report = {
        "extra_prompt": _stats(extra_prompt, out_extra_prompt),
        "issue_body": _stats(issue_body, out_issue_body),
        "pr_body": _stats(pr_body, out_pr_body),
        "pr_meta": _stats(in_pr_meta_json, out_pr_meta_json),
        "review_context": _stats(in_review_context_json, out_review_context_json),
    }

    total_input_bytes = (
        _len_bytes(extra_prompt)
        + _len_bytes(issue_body)
        + _len_bytes(pr_body)
        + _len_bytes(in_pr_meta_json)
        + _len_bytes(in_review_context_json)
    )
    total_output_bytes = _total_bytes()

    return GoverningResult(
        extra_prompt=out_extra_prompt,
        issue_body=out_issue_body,
        pr_body=out_pr_body,
        pr_meta_json=out_pr_meta_json,
        review_context_json=out_review_context_json,
        trim_report=trim_report,
        total_input_bytes=total_input_bytes,
        total_output_bytes=total_output_bytes,
        budget_bytes=budget_bytes,
    )
