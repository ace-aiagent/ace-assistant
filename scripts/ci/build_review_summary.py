#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.ci._io_utils import read_json

_SEV_MAP = {"high": "🔴", "medium": "🟡", "low": "🔵"}


def _render_non_blocking_suggestion(suggestion: dict[str, Any], lines: list[str]) -> None:
    file_path = suggestion.get("file", "")
    description = suggestion.get("description", "")
    severity = suggestion.get("severity", "low").lower()
    line_nums: list[int] = suggestion.get("lines") or []

    emoji = _SEV_MAP.get(severity, "⚫")

    location = f"`{file_path}`" if file_path else ""
    if line_nums:
        line_str = ", ".join(str(n) for n in line_nums)
        location += f" (L{line_str})"

    header_parts = [emoji]
    if location:
        header_parts.append(location)
    header = " ".join(header_parts)

    lines.append(f"- {header}: {description}" if description else f"- {header}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result: dict[str, Any] = read_json(args.result_file)
    decision = result.get("decision", "")
    summary = result.get("summary", "")

    lines: list[str] = []

    if decision == "APPROVED":
        lines.append("## ✅ Approved")
        lines.append("")
        lines.append(summary)
        lines.append("")
    elif decision == "CHANGES_REQUESTED":
        lines.append("## ⚠️ Changes Requested")
        lines.append("")
        lines.append(summary)
        lines.append("")

        blocking = result.get("blocking_issues") or []
        if blocking:
            lines.append("### Blocking Issues")
            lines.append("")
            for item in blocking:
                severity = item.get("severity", "unknown").lower()
                title = item.get("title", "")
                why = item.get("why", "")
                suggested_fix = item.get("suggested_fix", "")

                sev_map = _SEV_MAP
                emoji = sev_map.get(severity, "⚫")
                badge = f"**[{severity.upper()}]**"

                lines.append(f"#### {emoji} {badge} {title}")
                lines.append("")
                lines.append(why)
                lines.append("")

                if suggested_fix:
                    has_newline = "\n" in suggested_fix
                    is_long = len(suggested_fix) > 150
                    if has_newline or is_long:
                        lines.append("<details>")
                        lines.append("<summary>Suggested fix</summary>")
                        lines.append("")
                        lines.append(suggested_fix)
                        lines.append("")
                        lines.append("</details>")
                    else:
                        lines.append(f"**Suggested fix:** {suggested_fix}")
                lines.append("")

        non_blocking = result.get("non_blocking_suggestions") or []
        if non_blocking:
            lines.append("### Non-blocking Suggestions")
            lines.append("")
            for suggestion in non_blocking:
                if isinstance(suggestion, dict):
                    _render_non_blocking_suggestion(suggestion, lines)
                else:
                    lines.append(f"- {suggestion}")
            lines.append("")

    checks = result.get("recommended_checks") or []
    if checks:
        lines.append("### Recommended Checks")
        lines.append("")
        lines.append("```")
        for check in checks:
            lines.append(check)
        lines.append("```")
        lines.append("")

    body = "\n".join(lines).rstrip()
    Path(args.output).write_text(body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
