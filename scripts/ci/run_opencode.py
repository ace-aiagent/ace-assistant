#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from scripts.ci._io_utils import write_json
from scripts.ci.result_protocol import (
    PROTOCOL_VERSION,
    ProtocolValidationError,
    normalize_diagnostics,
    unwrap_result,
    validate_envelope,
)


ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*(?:"|$)', re.DOTALL)
_RESULT_BLOCK_RE = re.compile(
    r"^[ \t]*AI_RESULT_BEGIN[ \t]*\r?\n(.*?)\r?\n[ \t]*AI_RESULT_END[ \t]*\r?$",
    re.MULTILINE | re.DOTALL,
)
_ENVELOPE_START_RE = re.compile(
    r'\{\s*"protocol_version"\s*:\s*"result-envelope\.v1"'
)


class ResultParseError(ValueError):
    def __init__(self, error_code: str, message: str, *, retriable: bool) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retriable = retriable


@dataclass(frozen=True)
class ParseResult:
    payload: dict[str, object]
    parser_mode: str
    fallback_used: bool
    legacy_fallback_reason: str | None


def _repair_json_newlines(text: str) -> str:
    """LLM 可能在 JSON 字符串值中输出 literal newline，导致 json.loads 失败。
    将 JSON 字符串值内部的真实换行替换为 \n 转义。"""

    def _fix_match(m: re.Match[str]) -> str:
        s = m.group(0)
        if "\n" not in s:
            return s
        inner = s[1:-1] if s.endswith('"') else s[1:]
        inner = inner.replace("\n", "\\n")
        end = '"' if s.endswith('"') else ""
        return f'"{inner}{end}'

    return _JSON_STRING_RE.sub(_fix_match, text)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _stream_pipe(pipe, *, dest, buf: list[str]) -> None:
    assert pipe is not None
    for line in pipe:
        dest.write(line)
        dest.flush()
        buf.append(line)


def _extract_payload_candidates(text: str) -> list[str]:
    return _RESULT_BLOCK_RE.findall(text)


_BEGIN_ONLY_RE = re.compile(r"^[ \t]*AI_RESULT_BEGIN[ \t]*\r?\n", re.MULTILINE)


def _strip_markdown_code_block(text: str) -> str:
    code_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    return text


def _try_parse_payload(raw_payload: str) -> dict[str, object] | None:
    for candidate in (raw_payload, _repair_json_newlines(raw_payload)):
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded
    return None


def _try_parse_incomplete_marker_payload(search_text: str) -> dict[str, object] | None:
    begin_matches = list(_BEGIN_ONLY_RE.finditer(search_text))
    if not begin_matches:
        return None

    tail = search_text[begin_matches[-1].end() :].strip()
    if not tail:
        return None

    normalized_tail = _strip_markdown_code_block(tail)
    parsed = _try_parse_payload(normalized_tail)
    if parsed is not None:
        return parsed

    try:
        decoded, _ = json.JSONDecoder().raw_decode(normalized_tail)
    except json.JSONDecodeError:
        return None

    if isinstance(decoded, dict):
        return decoded
    return None


def _has_unclosed_tail_begin(search_text: str) -> bool:
    begin_matches = list(_BEGIN_ONLY_RE.finditer(search_text))
    if not begin_matches:
        return False
    end_matches = list(re.finditer(r"^[ \t]*AI_RESULT_END[ \t]*\r?\n?", search_text, re.MULTILINE))
    if not end_matches:
        return True
    return begin_matches[-1].start() > end_matches[-1].start()


def _extract_text_from_jsonl(raw_stdout: str) -> str:
    """从 ``opencode run --format json`` 的 JSONL 事件流中提取 text 事件内容。

    text 事件格式: ``{"type":"text", "part":{"text":"<content>"}}``

    在 opencode JSONL 格式中，``type=text`` 事件全部来自 assistant（无 role 字段）。
    tool_use、tool_result 等事件使用不同的 type 值，不会被此函数采集。
    """
    parts: list[str] = []
    for line in raw_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "text":
            continue
        part = event.get("part")
        if isinstance(part, dict):
            text = part.get("text", "")
            if text:
                parts.append(text)
    return "".join(parts)


def _is_jsonl_event_stream(raw_stdout: str) -> bool:
    event_like_count = 0
    for line in raw_stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if isinstance(event_type, str) and event_type:
            event_like_count += 1
            if event_like_count >= 2:
                return True
    return False


def _get_max_attempts() -> int:
    raw = os.environ.get("OPENCODE_MAX_ATTEMPTS", "2")
    try:
        value = int(raw)
    except ValueError:
        return 2
    return value if value >= 1 else 1


def _protocol_mode() -> str:
    mode = os.environ.get("ACE_RESULT_PROTOCOL_MODE", "legacy").strip().lower()
    valid = {"legacy", "dual-read", "strict-envelope"}
    if mode not in valid:
        raise ValueError(f"Unknown ACE_RESULT_PROTOCOL_MODE: {mode!r}. Valid: {sorted(valid)}")
    return mode


def _parse_requested_mode(prompt: str, output_file: str) -> str:
    name = Path(output_file).name.lower()
    if "triage" in name:
        return "triage"
    if "review" in name:
        return "review"
    if "fix" in name:
        return "fix"

    lower_prompt = prompt.lower()
    if '"mode": "triage"' in lower_prompt or "strict bug triage agent" in lower_prompt:
        return "triage"
    if '"mode": "review"' in lower_prompt or "strict pull request reviewer" in lower_prompt:
        return "review"
    if '"mode": "fix"' in lower_prompt or "autonomous bug-fixing agent" in lower_prompt:
        return "fix"
    return "triage"


def _scan_balanced_json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return idx + 1
            continue

    return None


def _extract_envelope_candidates(search_text: str) -> tuple[list[str], bool]:
    candidates: list[str] = []
    starts = list(_ENVELOPE_START_RE.finditer(search_text))
    if not starts:
        return candidates, False

    has_incomplete_tail = False
    for idx, match in enumerate(starts):
        start = match.start()
        end = _scan_balanced_json_object_end(search_text, start)
        if end is None:
            if idx == len(starts) - 1:
                has_incomplete_tail = True
            continue
        candidates.append(search_text[start:end].strip())

    return candidates, has_incomplete_tail


def _parse_legacy_result(search_text: str) -> dict[str, object]:
    matches = _extract_payload_candidates(search_text)

    if _has_unclosed_tail_begin(search_text):
        incomplete_payload = _try_parse_incomplete_marker_payload(search_text)
        if incomplete_payload is not None:
            return incomplete_payload

    if not matches:
        incomplete_payload = _try_parse_incomplete_marker_payload(search_text)
        if incomplete_payload is not None:
            return incomplete_payload
        raise ResultParseError(
            "LEGACY_MARKER_MISSING",
            "Could not find AI_RESULT_BEGIN/AI_RESULT_END JSON payload.",
            retriable=True,
        )

    payload: dict[str, object] | None = None
    last_raw_payload = ""
    for candidate in reversed(matches):
        normalized_payload = _strip_markdown_code_block(candidate.strip())
        last_raw_payload = normalized_payload
        parsed = _try_parse_payload(normalized_payload)
        if parsed is not None:
            payload = parsed
            break

    if payload is None:
        print(f"Raw payload:\n{last_raw_payload}", file=sys.stderr)
        raise ResultParseError(
            "LEGACY_JSON_PARSE_FAILED",
            "Failed to parse JSON between AI_RESULT markers.",
            retriable=True,
        )

    return payload


def _parse_result_with_meta(
    combined: str,
    *,
    is_jsonl: bool,
    protocol_mode: str,
    requested_mode: str,
) -> ParseResult:
    search_text = _extract_text_from_jsonl(combined) if is_jsonl else combined

    if protocol_mode == "legacy":
        payload = _parse_legacy_result(search_text)
        return ParseResult(
            payload=payload,
            parser_mode="legacy",
            fallback_used=False,
            legacy_fallback_reason=None,
        )

    envelope_candidates, has_incomplete_tail = _extract_envelope_candidates(search_text)

    if has_incomplete_tail:
        raise ResultParseError(
            "INCOMPLETE_ENVELOPE_TAIL",
            "Latest assistant tail contains incomplete result envelope.",
            retriable=True,
        )

    if envelope_candidates:
        last_envelope = envelope_candidates[-1]
        parsed_envelope = _try_parse_payload(last_envelope)
        if parsed_envelope is None:
            raise ResultParseError(
                "ENVELOPE_JSON_PARSE_FAILED",
                "Failed to parse JSON result envelope.",
                retriable=True,
            )
        validate_envelope(parsed_envelope, requested_mode=requested_mode)
        if parsed_envelope.get("status") == "error":
            raise ResultParseError(
                "STATUS_ERROR",
                "Envelope status=error: AI reported a processing error.",
                retriable=False,
            )
        payload = unwrap_result(parsed_envelope)
        return ParseResult(
            payload=payload,
            parser_mode="envelope",
            fallback_used=False,
            legacy_fallback_reason=None,
        )

    if protocol_mode == "strict-envelope":
        raise ProtocolValidationError(
            "MISSING_ENVELOPE",
            f"未找到 protocol_version={PROTOCOL_VERSION} 的 envelope",
        )

    payload = _parse_legacy_result(search_text)
    return ParseResult(
        payload=payload,
        parser_mode="legacy",
        fallback_used=True,
        legacy_fallback_reason="no_envelope_candidates",
    )


def _is_retriable_parse_error(exc: Exception) -> bool:
    if isinstance(exc, ResultParseError):
        return exc.retriable
    return False


def _parse_result(combined: str, *, is_jsonl: bool) -> dict[str, object]:
        try:
            parse_result = _parse_result_with_meta(
                combined_for_parse,
                is_jsonl=is_jsonl,
                protocol_mode=protocol_mode,
                requested_mode=requested_mode,
            )
        except (ResultParseError, ProtocolValidationError) as exc:
            last_parse_error = exc
            if attempt < max_attempts and _is_retriable_parse_error(exc):
                continue

            if output_path.exists():
                output_path.unlink()

            raw_log_path.write_text("\n\n".join(attempt_logs), encoding="utf-8")
            error_code = exc.error_code
            _write_diagnostics(
                parser_mode="legacy" if protocol_mode == "legacy" else "envelope",
                fallback_used=False,
                attempt=attempt,
                legacy_fallback_reason=None,
                error_code=error_code,
            )
            raise SystemExit(str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    args = parser.parse_args()

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    protocol_mode = _protocol_mode()
    requested_mode = _parse_requested_mode(prompt, args.output_file)

    cmd = ["opencode", "run", "--format", "json", prompt]

    env = os.environ.copy()
    env.setdefault("CI", "1")

    max_attempts = _get_max_attempts()
    output_path = Path(args.output_file)
    raw_log_path = Path(args.output_file).with_suffix(".raw.txt")
    diagnostics_path = Path(f"{args.output_file}.diagnostics.json")
    attempt_logs: list[str] = []
    last_parse_error: Exception | None = None

    def _write_diagnostics(
        *,
        parser_mode: str,
        fallback_used: bool,
        attempt: int,
        legacy_fallback_reason: str | None,
        error_code: str | None,
    ) -> None:
        context_trimmed = False
        trim_report = None
        trim_meta_path = Path(str(args.prompt_file) + ".trim_meta.json")
        if trim_meta_path.exists():
            try:
                tm = json.loads(trim_meta_path.read_text(encoding="utf-8"))
                context_trimmed = bool(tm.get("context_trimmed", False))
                trim_report = tm.get("trim_report")
            except Exception:
                pass
        diagnostics = normalize_diagnostics(
            {"mode": requested_mode},
            parser_mode=parser_mode,
            fallback_used=fallback_used,
            attempt=attempt,
            max_attempts=max_attempts,
            context_trimmed=context_trimmed,
            trim_report=trim_report,
            legacy_fallback_reason=legacy_fallback_reason,
            raw_log_path=str(raw_log_path),
            error_code=error_code,
        )
        write_json(diagnostics_path, diagnostics, indent=2)

    for attempt in range(1, max_attempts + 1):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []

        stderr_thread = threading.Thread(
            target=_stream_pipe,
            args=(proc.stderr,),
            kwargs={"dest": sys.stderr, "buf": stderr_buf},
        )
        stderr_thread.start()

        assert proc.stdout is not None
        _stream_pipe(proc.stdout, dest=sys.stdout, buf=stdout_buf)

        stderr_thread.join()
        returncode = proc.wait()

        raw_stdout = "".join(stdout_buf)
        raw_stderr = "".join(stderr_buf)

        is_jsonl = _is_jsonl_event_stream(raw_stdout)

        if is_jsonl:
            combined_for_log = strip_ansi(raw_stdout + "\n" + raw_stderr)
            combined_for_parse = raw_stdout
        else:
            combined_for_log = strip_ansi(raw_stdout + "\n" + raw_stderr)
            combined_for_parse = combined_for_log

        attempt_logs.append(f"=== attempt {attempt}/{max_attempts} ===\n{combined_for_log}")

        if returncode != 0:
            if output_path.exists():
                output_path.unlink()
            raw_log_path.write_text("\n\n".join(attempt_logs), encoding="utf-8")
            _write_diagnostics(
                parser_mode="legacy" if protocol_mode == "legacy" else "envelope",
                fallback_used=False,
                attempt=attempt,
                legacy_fallback_reason=None,
                error_code="PROCESS_EXIT_NON_ZERO",
            )
            raise SystemExit(returncode)

        try:
            parse_result = _parse_result_with_meta(
                combined_for_parse,
                is_jsonl=is_jsonl,
                protocol_mode=protocol_mode,
                requested_mode=requested_mode,
            )
        except (ResultParseError, ProtocolValidationError) as exc:
            last_parse_error = exc
            if attempt < max_attempts and _is_retriable_parse_error(exc):
                continue

            if output_path.exists():
                output_path.unlink()

            raw_log_path.write_text("\n\n".join(attempt_logs), encoding="utf-8")
            error_code = exc.error_code
            _write_diagnostics(
                parser_mode="legacy" if protocol_mode == "legacy" else "envelope",
                fallback_used=False,
                attempt=attempt,
                legacy_fallback_reason=None,
                error_code=error_code,
            )
            raise SystemExit(str(exc)) from exc

        write_json(args.output_file, parse_result.payload, indent=2)
        _write_diagnostics(
            parser_mode=parse_result.parser_mode,
            fallback_used=parse_result.fallback_used,
            attempt=attempt,
            legacy_fallback_reason=parse_result.legacy_fallback_reason,
            error_code=None,
        )
        return

    if last_parse_error is not None:
        raw_log_path.write_text("\n\n".join(attempt_logs), encoding="utf-8")
        raise SystemExit(str(last_parse_error))
    raise SystemExit("Could not parse opencode output.")


if __name__ == "__main__":
    main()
