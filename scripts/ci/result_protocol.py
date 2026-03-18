#!/usr/bin/env python3
from __future__ import annotations

from typing import Any


PROTOCOL_VERSION = "result-envelope.v1"
VALID_MODES = {"triage", "fix", "review"}
VALID_STATUSES = {"ok", "error"}
VALID_TOP_LEVEL_FIELDS = {
    "protocol_version",
    "mode",
    "status",
    "result",
    "diagnostics",
}


class ProtocolValidationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _require_mapping(envelope: dict[str, Any]) -> None:
    if not isinstance(envelope, dict):
        raise ProtocolValidationError("MISSING_RESULT", "envelope 必须是 JSON 对象")


def validate_envelope(envelope: dict, requested_mode: str) -> None:
    _require_mapping(envelope)

    extra_fields = set(envelope.keys()) - VALID_TOP_LEVEL_FIELDS
    if extra_fields:
        raise ProtocolValidationError(
            "EXTRA_FIELDS",
            f"envelope 包含不允许的顶层字段: {sorted(extra_fields)}",
        )

    if "protocol_version" not in envelope:
        raise ProtocolValidationError("MISSING_PROTOCOL_VERSION", "缺少 protocol_version")

    if envelope["protocol_version"] != PROTOCOL_VERSION:
        raise ProtocolValidationError(
            "WRONG_PROTOCOL_VERSION",
            f"protocol_version 必须为 {PROTOCOL_VERSION}",
        )

    if "mode" not in envelope:
        raise ProtocolValidationError("MISSING_MODE", "缺少 mode")

    mode = envelope["mode"]
    if mode not in VALID_MODES:
        raise ProtocolValidationError("INVALID_MODE", f"mode 非法: {mode!r}")

    if requested_mode not in VALID_MODES:
        raise ProtocolValidationError("INVALID_MODE", f"requested_mode 非法: {requested_mode!r}")

    if mode != requested_mode:
        raise ProtocolValidationError(
            "MODE_MISMATCH",
            f"envelope.mode={mode!r} 与 requested_mode={requested_mode!r} 不一致",
        )

    if "status" not in envelope:
        raise ProtocolValidationError("MISSING_STATUS", "缺少 status")

    status = envelope["status"]
    if status not in VALID_STATUSES:
        raise ProtocolValidationError("INVALID_STATUS", f"status 非法: {status!r}")

    if "result" not in envelope:
        raise ProtocolValidationError("MISSING_RESULT", "缺少 result")

    if "diagnostics" not in envelope:
        raise ProtocolValidationError("MISSING_DIAGNOSTICS", "缺少 diagnostics")


def unwrap_result(envelope: dict) -> dict:
    result = envelope.get("result")
    if not isinstance(result, dict):
        raise ProtocolValidationError("MISSING_RESULT", "result 必须是对象")
    return result


def normalize_diagnostics(
    envelope: dict,
    *,
    parser_mode: str,
    fallback_used: bool,
    attempt: int,
    max_attempts: int,
    context_trimmed: bool,
    trim_report: dict | None,
    legacy_fallback_reason: str | None,
    raw_log_path: str,
    error_code: str | None,
) -> dict:
    mode = envelope.get("mode")
    requested_mode = mode if mode in VALID_MODES else "unknown"

    return {
        "protocol_version": PROTOCOL_VERSION,
        "requested_mode": requested_mode,
        "parser_mode": parser_mode,
        "fallback_used": fallback_used,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "context_trimmed": context_trimmed,
        "trim_report": trim_report,
        "legacy_fallback_reason": legacy_fallback_reason,
        "raw_log_path": raw_log_path,
        "error_code": error_code,
    }
