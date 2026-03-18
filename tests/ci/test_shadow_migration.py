from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci import run_opencode
from scripts.ci.prompt_governor import govern
from scripts.ci.result_protocol import (
    PROTOCOL_VERSION,
    ProtocolValidationError,
    normalize_diagnostics,
    unwrap_result,
    validate_envelope,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "result_protocol"

ENVELOPE_MATRIX = [
    ("triage_envelope_ok.json", "triage"),
    ("fix_issue_envelope_ok.json", "fix"),
    ("fix_retry_envelope_ok.json", "fix"),
    ("review_envelope_ok.json", "review"),
]

EXPECTED_RESULT_FIXTURES = {
    "triage_envelope_ok.json": "triage_result_expected.json",
    "fix_issue_envelope_ok.json": "fix_issue_result_expected.json",
    "fix_retry_envelope_ok.json": "fix_retry_result_expected.json",
    "review_envelope_ok.json": "review_result_expected.json",
}

REQUIRED_WORKFLOW_FIELDS = {
    "triage_envelope_ok.json": {"verdict", "reason"},
    "fix_issue_envelope_ok.json": {"summary", "changed_files", "verification", "followups"},
    "fix_retry_envelope_ok.json": {"summary", "changed_files", "verification", "remaining_risks"},
    "review_envelope_ok.json": {"decision", "summary", "blocking_issues", "recommended_checks"},
}

TRIAGE_COMPATIBILITY_ALTERNATIVES = [
    {"label", "suggested_title"},
    {"fix_strategy", "branch_slug"},
]

REQUIRED_DIAGNOSTICS_FIELDS = {
    "protocol_version",
    "requested_mode",
    "parser_mode",
    "fallback_used",
    "attempt",
    "max_attempts",
    "context_trimmed",
    "trim_report",
    "legacy_fallback_reason",
    "raw_log_path",
    "error_code",
}


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _assert_workflow_contract(payload: dict, *, fixture_name: str) -> None:
    missing = sorted(REQUIRED_WORKFLOW_FIELDS[fixture_name] - set(payload.keys()))
    if missing:
        raise ProtocolValidationError(
            "CONTRACT_DRIFT",
            f"{fixture_name} 缺少 workflow-facing 必需字段: {missing}",
        )

    if fixture_name == "triage_envelope_ok.json":
        if not any(option.issubset(payload.keys()) for option in TRIAGE_COMPATIBILITY_ALTERNATIVES):
            raise ProtocolValidationError(
                "CONTRACT_DRIFT",
                "triage 结果缺少兼容字段组合：需满足(label+suggested_title)或(fix_strategy+branch_slug)",
            )


@pytest.mark.parametrize(("fixture_name", "requested_mode"), ENVELOPE_MATRIX)
def test_shadow_envelope_fixtures_zero_fallback_in_dual_read(
    monkeypatch: pytest.MonkeyPatch,
    fixture_name: str,
    requested_mode: str,
) -> None:
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "dual-read")
    envelope = _load_fixture(fixture_name)

    parsed = run_opencode._parse_result_with_meta(
        json.dumps(envelope, ensure_ascii=False),
        is_jsonl=False,
        protocol_mode=run_opencode._protocol_mode(),
        requested_mode=requested_mode,
    )

    assert parsed.parser_mode == "envelope"
    assert parsed.fallback_used is False
    assert parsed.legacy_fallback_reason is None


@pytest.mark.parametrize(("fixture_name", "requested_mode"), ENVELOPE_MATRIX)
def test_shadow_result_schema_compatibility_for_workflow_fields(
    fixture_name: str,
    requested_mode: str,
) -> None:
    envelope = _load_fixture(fixture_name)

    validate_envelope(envelope, requested_mode=requested_mode)
    payload = unwrap_result(envelope)
    _assert_workflow_contract(payload, fixture_name=fixture_name)

    expected_payload = _load_fixture(EXPECTED_RESULT_FIXTURES[fixture_name])
    assert payload == expected_payload


def test_shadow_diagnostics_sidecar_validity() -> None:
    diagnostics = normalize_diagnostics(
        {"mode": "triage"},
        parser_mode="envelope",
        fallback_used=False,
        attempt=1,
        max_attempts=2,
        context_trimmed=True,
        trim_report={"section": {"input_bytes": 100, "output_bytes": 70, "trimmed_bytes": 30}},
        legacy_fallback_reason=None,
        raw_log_path="/tmp/triage_result.raw.txt",
        error_code=None,
    )

    assert diagnostics["protocol_version"] == PROTOCOL_VERSION
    assert diagnostics["requested_mode"] == "triage"
    assert REQUIRED_DIAGNOSTICS_FIELDS.issubset(diagnostics.keys())


def test_shadow_legacy_fixture_falls_back_under_dual_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACE_RESULT_PROTOCOL_MODE", "dual-read")
    legacy_text = "AI_RESULT_BEGIN\n{\"ok\": true}\nAI_RESULT_END\n"

    parsed = run_opencode._parse_result_with_meta(
        legacy_text,
        is_jsonl=False,
        protocol_mode=run_opencode._protocol_mode(),
        requested_mode="triage",
    )

    assert parsed.payload == {"ok": True}
    assert parsed.fallback_used is True
    assert parsed.parser_mode == "legacy"


def test_shadow_contract_drift_detects_missing_review_decision() -> None:
    drifted_review = _load_fixture("review_envelope_ok.json")
    drifted_review["result"].pop("decision", None)

    with pytest.raises(ProtocolValidationError) as exc_info:
        run_opencode._parse_result_with_meta(
            json.dumps(drifted_review, ensure_ascii=False),
            is_jsonl=False,
            protocol_mode="strict-envelope",
            requested_mode="review",
        )

    assert exc_info.value.error_code == "INVALID_RESULT_SCHEMA"


def test_shadow_trim_report_contains_non_zero_trim_events() -> None:
    report = govern(
        "retry-fix",
        extra_prompt="x" * 1800,
        issue_body="i" * 5000,
        pr_body="p" * 5000,
        pr_meta={"meta": "m" * 2500},
        review_context={
            "decision": "CHANGES_REQUESTED",
            "summary": "s" * 5000,
            "blocking_issues": [{"title": "critical", "severity": "high", "why": "w" * 1200, "suggested_fix": "f" * 1200}],
            "recommended_checks": ["cmd-" + ("c" * 800) for _ in range(25)],
        },
    ).trim_report

    trim_events = [section for section in report.values() if section["trimmed_bytes"] > 0]
    assert trim_events
