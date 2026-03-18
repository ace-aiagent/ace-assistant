from __future__ import annotations

import json

import pytest


def test_govern_returns_governing_result_type() -> None:
    from scripts.ci.prompt_governor import GoverningResult, govern

    result = govern("triage")
    assert isinstance(result, GoverningResult)


def test_govern_idempotent_same_input_twice() -> None:
    from scripts.ci.prompt_governor import govern

    payload = {
        "decision": "CHANGES_REQUESTED",
        "summary": "summary",
        "blocking_issues": [{"title": "A", "severity": "high"}],
        "recommended_checks": ["lint", "test"],
    }
    first = govern(
        "review",
        extra_prompt="follow rules",
        issue_body="issue",
        pr_body="pr body",
        pr_meta={"round": 2},
        review_context=payload,
    )
    second = govern(
        "review",
        extra_prompt="follow rules",
        issue_body="issue",
        pr_body="pr body",
        pr_meta={"round": 2},
        review_context=payload,
    )
    assert first == second


def test_govern_unknown_mode_raises_value_error() -> None:
    from scripts.ci.prompt_governor import govern

    with pytest.raises(ValueError, match="Unknown governor mode"):
        govern("unknown")


def test_extra_prompt_capped_at_1024_bytes() -> None:
    from scripts.ci.prompt_governor import CAP_EXTRA_PROMPT_BYTES, govern

    result = govern("triage", extra_prompt="x" * (CAP_EXTRA_PROMPT_BYTES + 400))
    assert len(result.extra_prompt.encode("utf-8")) <= CAP_EXTRA_PROMPT_BYTES + len("...".encode("utf-8"))
    assert result.trim_report["extra_prompt"]["trimmed_bytes"] > 0


def test_issue_body_capped_at_4096_bytes() -> None:
    from scripts.ci.prompt_governor import CAP_ISSUE_BODY_BYTES, govern

    result = govern("triage", issue_body="i" * (CAP_ISSUE_BODY_BYTES + 400))
    assert len(result.issue_body.encode("utf-8")) <= CAP_ISSUE_BODY_BYTES + len("...".encode("utf-8"))
    assert result.trim_report["issue_body"]["trimmed_bytes"] > 0


def test_pr_body_capped_at_4096_bytes() -> None:
    from scripts.ci.prompt_governor import CAP_PR_BODY_BYTES, govern

    result = govern("triage", pr_body="p" * (CAP_PR_BODY_BYTES + 400))
    assert len(result.pr_body.encode("utf-8")) <= CAP_PR_BODY_BYTES + len("...".encode("utf-8"))
    assert result.trim_report["pr_body"]["trimmed_bytes"] > 0


def test_pr_meta_capped_at_1536_bytes() -> None:
    from scripts.ci.prompt_governor import CAP_PR_META_BYTES, govern

    result = govern("triage", pr_meta={"k": "m" * 4_000})
    assert len(result.pr_meta_json.encode("utf-8")) <= CAP_PR_META_BYTES + len("...".encode("utf-8"))
    assert result.trim_report["pr_meta"]["trimmed_bytes"] > 0


def test_review_context_capped_at_3072_bytes() -> None:
    from scripts.ci.prompt_governor import CAP_REVIEW_CONTEXT_BYTES, govern

    result = govern("triage", review_context={"summary": "r" * 10_000, "blocking_issues": []})
    assert len(result.review_context_json.encode("utf-8")) <= CAP_REVIEW_CONTEXT_BYTES + len("...".encode("utf-8"))
    assert result.trim_report["review_context"]["trimmed_bytes"] > 0


def test_trim_order_recommended_checks_first() -> None:
    from scripts.ci.prompt_governor import govern

    checks = [f"check-{i}-" + ("x" * 500) for i in range(20)]
    review_context = {
        "decision": "CHANGES_REQUESTED",
        "summary": "s",
        "blocking_issues": [{"title": "must-fix", "severity": "high", "why": "w", "suggested_fix": "f"}],
        "recommended_checks": checks,
    }

    result = govern("triage", pr_body="small-pr-body", review_context=review_context)
    governed_ctx = json.loads(result.review_context_json)

    assert result.pr_body == "small-pr-body"
    assert len(governed_ctx.get("recommended_checks", [])) < len(checks)


def test_blocking_issues_never_dropped() -> None:
    from scripts.ci.prompt_governor import govern

    blocking = [
        {
            "title": f"title-{i}",
            "severity": "high" if i % 2 == 0 else "medium",
            "why": "w" * 2_000,
            "suggested_fix": "f" * 2_000,
        }
        for i in range(5)
    ]
    review_context = {
        "decision": "CHANGES_REQUESTED",
        "summary": "s" * 2_000,
        "blocking_issues": blocking,
        "recommended_checks": ["c" * 600 for _ in range(20)],
    }

    result = govern("triage", review_context=review_context)
    governed_ctx = json.loads(result.review_context_json)
    governed_blocking = governed_ctx.get("blocking_issues", [])

    for i, issue in enumerate(governed_blocking):
        assert issue.get("title") == blocking[i]["title"]
        assert issue.get("severity") == blocking[i]["severity"]


def test_trim_report_records_all_sections() -> None:
    from scripts.ci.prompt_governor import govern

    result = govern(
        "triage",
        extra_prompt="x" * 2_000,
        issue_body="i" * 5_000,
        pr_body="p" * 5_000,
        pr_meta={"k": "m" * 4_000},
        review_context={"summary": "r" * 10_000, "blocking_issues": [], "recommended_checks": ["c" * 1_000] * 10},
    )

    keys = {"extra_prompt", "issue_body", "pr_body", "pr_meta", "review_context"}
    assert set(result.trim_report.keys()) == keys
    for key in keys:
        stats = result.trim_report[key]
        assert set(stats.keys()) == {"input_bytes", "output_bytes", "trimmed_bytes"}
        assert stats["input_bytes"] >= stats["output_bytes"]
        assert stats["trimmed_bytes"] == stats["input_bytes"] - stats["output_bytes"]


def test_no_trim_small_inputs_zero_trimmed_bytes() -> None:
    from scripts.ci.prompt_governor import govern

    result = govern(
        "review",
        extra_prompt="short",
        issue_body="issue",
        pr_body="body",
        pr_meta={"round": 1},
        review_context={
            "decision": "APPROVED",
            "summary": "ok",
            "blocking_issues": [{"title": "t", "severity": "low", "why": "w", "suggested_fix": "s"}],
            "recommended_checks": ["lint"],
        },
    )

    for section in result.trim_report.values():
        assert section["trimmed_bytes"] == 0


def test_retry_fix_budget_tighter_than_issue_fix() -> None:
    from scripts.ci.prompt_governor import govern

    shared_review = {
        "decision": "CHANGES_REQUESTED",
        "summary": "s" * 3_000,
        "blocking_issues": [
            {"title": f"title-{i}", "severity": "high", "why": "w" * 1_000, "suggested_fix": "f" * 1_000}
            for i in range(5)
        ],
        "recommended_checks": ["c" * 500 for _ in range(10)],
    }
    kwargs = {
        "extra_prompt": "x" * 2_000,
        "issue_body": "i" * 6_000,
        "pr_body": "p" * 6_000,
        "pr_meta": {"k": "m" * 4_000},
        "review_context": shared_review,
    }

    issue_fix = govern("issue-fix", **kwargs)
    retry_fix = govern("retry-fix", **kwargs)

    assert retry_fix.budget_bytes < issue_fix.budget_bytes
    assert retry_fix.total_output_bytes <= retry_fix.budget_bytes
    assert issue_fix.total_output_bytes <= issue_fix.budget_bytes
    assert retry_fix.total_output_bytes <= issue_fix.total_output_bytes


def test_retry_fix_pr_body_and_review_context_both_capped() -> None:
    from scripts.ci.prompt_governor import CAP_PR_BODY_BYTES, CAP_REVIEW_CONTEXT_BYTES, govern

    result = govern(
        "retry-fix",
        extra_prompt="x" * 2_000,
        issue_body="i" * 6_000,
        pr_body="p" * 8_000,
        pr_meta={"k": "m" * 4_000},
        review_context={
            "decision": "CHANGES_REQUESTED",
            "summary": "s" * 6_000,
            "blocking_issues": [{"title": "must-fix", "severity": "high", "why": "w" * 1_000, "suggested_fix": "f" * 1_000}],
            "recommended_checks": ["c" * 600 for _ in range(20)],
        },
    )

    assert len(result.pr_body.encode("utf-8")) <= CAP_PR_BODY_BYTES + len("...".encode("utf-8"))
    assert len(result.review_context_json.encode("utf-8")) <= CAP_REVIEW_CONTEXT_BYTES + len("...".encode("utf-8"))
    assert result.total_output_bytes <= result.budget_bytes


def test_unicode_text_truncated_at_valid_utf8_boundary() -> None:
    from scripts.ci.prompt_governor import govern

    text = "你" * 2_000
    result = govern("triage", extra_prompt=text)

    encoded = result.extra_prompt.encode("utf-8")
    decoded = encoded.decode("utf-8")
    assert decoded == result.extra_prompt
    assert result.extra_prompt.endswith("...")


def test_retry_fix_review_context_reduced_30_percent_and_blocking_intact() -> None:
    from scripts.ci.prompt_governor import govern

    blocking = [
        {"title": f"critical-{i}", "severity": "high", "why": "w" * 1200, "suggested_fix": "f" * 1200}
        for i in range(4)
    ]
    raw_context = {
        "decision": "CHANGES_REQUESTED",
        "summary": "s" * 5000,
        "blocking_issues": blocking,
        "recommended_checks": ["check-" + ("c" * 800) for _ in range(25)],
    }

    raw_review_json = json.dumps(raw_context, ensure_ascii=False, separators=(",", ":"))
    result = govern(
        "retry-fix",
        extra_prompt="x" * 1800,
        issue_body="i" * 5000,
        pr_body="p" * 5000,
        pr_meta={"meta": "m" * 2000},
        review_context=raw_context,
    )

    raw_bytes = len(raw_review_json.encode("utf-8"))
    governed_bytes = len(result.review_context_json.encode("utf-8"))
    assert governed_bytes <= int(raw_bytes * 0.7)

    governed_context = json.loads(result.review_context_json)
    governed_blocking = governed_context.get("blocking_issues", [])
    assert len(governed_blocking) == len(blocking)
    for idx, issue in enumerate(governed_blocking):
        assert issue["title"] == blocking[idx]["title"]
        assert issue["severity"] == blocking[idx]["severity"]
