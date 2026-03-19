"""Tests for fix history shell logic in reusable-fix.yml.

This module tests the jq-based fix history building logic that handles:
1. Missing fix_result.json - should skip creating history entry
2. Array type changed_files - should join with ", "
3. Non-array changed_files - should convert to string
4. Missing changed_files - should result in empty string
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest


class TestFixHistoryLogic:
    """Test the fix history building logic from reusable-fix.yml.

    The shell logic being tested:
    if [[ -f fix_result.json ]]; then
        fix_summary_text="$(jq -r '.summary // ""' fix_result.json)"
        changed_files=""
        if jq -e '(.changed_files | type) == "array"' fix_result.json >/dev/null 2>&1; then
            changed_files="$(jq -r '.changed_files | join(", ")' fix_result.json | head -c 100)"
        elif jq -e 'has("changed_files")' fix_result.json >/dev/null 2>&1; then
            changed_files="$(jq -r '.changed_files | tostring' fix_result.json | head -c 100)"
        fi
        # Build fix_entry...
    else
        # Skip adding fix history entry
    fi
    """

    def _run_jq(self, json_file: Path, query: str) -> tuple[str, int]:
        """Run jq query on JSON file and return (output, exit_code)."""
        result = subprocess.run(
            ["jq", "-r", query, str(json_file)],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip(), result.returncode

    def _run_jq_check(self, json_file: Path, query: str) -> bool:
        """Run jq with -e flag and return True if exit code is 0."""
        result = subprocess.run(
            ["jq", "-e", query, str(json_file)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _build_fix_entry(
        self,
        fix_result_file: Path | None,
        fix_round: str = "1",
    ) -> dict[str, Any] | None:
        """Simulate the shell logic for building fix history entry.

        Returns the fix_entry dict if fix_result.json exists, otherwise None.
        """
        # Simulate: if [[ -f fix_result.json ]]; then
        if fix_result_file is None or not fix_result_file.exists():
            return None

        # Simulate: fix_summary_text="$(jq -r '.summary // ""' fix_result.json)"
        summary, _ = self._run_jq(fix_result_file, '.summary // ""')

        # Simulate: changed_files validation logic
        changed_files = ""
        is_array = self._run_jq_check(fix_result_file, '(.changed_files | type) == "array"')
        has_field = self._run_jq_check(fix_result_file, 'has("changed_files")')

        if is_array:
            # changed_files is array - join it
            changed_files, _ = self._run_jq(fix_result_file, '.changed_files | join(", ")')
            changed_files = changed_files[:100]  # head -c 100
        elif has_field:
            # changed_files exists but is not array - convert to string
            changed_files, _ = self._run_jq(fix_result_file, '.changed_files | tostring')
            changed_files = changed_files[:100]  # head -c 100

        # Build the entry
        return {
            "round": int(fix_round),
            "summary": summary[:200],
            "changed_files": changed_files,
        }

    def test_missing_fix_result_file_returns_none(self, tmp_path: Path) -> None:
        """When fix_result.json doesn't exist, should return None (skip entry)."""
        result = self._build_fix_entry(None)
        assert result is None

        non_existent = tmp_path / "non_existent.json"
        result = self._build_fix_entry(non_existent)
        assert result is None

    def test_changed_files_as_array(self, tmp_path: Path) -> None:
        """When changed_files is array, should join with ', '."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            "changed_files": ["file1.py", "file2.py", "file3.py"],
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert result["changed_files"] == "file1.py, file2.py, file3.py"
        assert result["summary"] == "Fixed the bug"

    def test_changed_files_as_string(self, tmp_path: Path) -> None:
        """When changed_files is string (malformed), should convert to string without error."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            "changed_files": "file1.py",  # Malformed: should be array
        }))

        # This should not raise an error
        result = self._build_fix_entry(fix_result)

        assert result is not None
        # String is returned as-is by jq -r (raw output)
        assert result["changed_files"] == "file1.py"

    def test_changed_files_as_number(self, tmp_path: Path) -> None:
        """When changed_files is number (malformed), should convert to string."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            "changed_files": 42,  # Malformed: should be array
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert result["changed_files"] == "42"

    def test_missing_changed_files(self, tmp_path: Path) -> None:
        """When changed_files field is missing, should result in empty string."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            # No changed_files field
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert result["changed_files"] == ""

    def test_empty_changed_files_array(self, tmp_path: Path) -> None:
        """When changed_files is empty array, should result in empty string."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            "changed_files": [],
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert result["changed_files"] == ""

    def test_changed_files_truncation(self, tmp_path: Path) -> None:
        """When changed_files exceeds 100 chars, should be truncated."""
        fix_result = tmp_path / "fix_result.json"
        long_files = [f"very_long_filename_{i}.py" for i in range(10)]
        fix_result.write_text(json.dumps({
            "summary": "Fixed the bug",
            "changed_files": long_files,
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert len(result["changed_files"]) <= 100

    def test_summary_truncation(self, tmp_path: Path) -> None:
        """When summary exceeds 200 chars, should be truncated."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "x" * 500,  # Very long summary
            "changed_files": ["file.py"],
        }))

        result = self._build_fix_entry(fix_result)

        assert result is not None
        assert len(result["summary"]) <= 200

    def test_jq_type_check_array(self, tmp_path: Path) -> None:
        """Test jq type check for array."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({"changed_files": ["a", "b"]}))

        is_array = self._run_jq_check(fix_result, '(.changed_files | type) == "array"')
        assert is_array is True

    def test_jq_type_check_string(self, tmp_path: Path) -> None:
        """Test jq type check for string (should fail array check)."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({"changed_files": "abc"}))

        is_array = self._run_jq_check(fix_result, '(.changed_files | type) == "array"')
        assert is_array is False

    def test_jq_has_check(self, tmp_path: Path) -> None:
        """Test jq has check for field existence."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({"other_field": "value"}))

        has_changed_files = self._run_jq_check(fix_result, 'has("changed_files")')
        assert has_changed_files is False

        has_other = self._run_jq_check(fix_result, 'has("other_field")')
        assert has_other is True


class TestFixHistoryIntegration:
    """Integration tests simulating the full workflow scenarios."""

    def test_pr_retry_successful_fix(self, tmp_path: Path) -> None:
        """Simulate a successful PR retry fix with valid changed_files array."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed null pointer exception in auth module",
            "changed_files": ["src/auth.py", "tests/test_auth.py"],
            "confidence": "high",
        }))

        # Simulate the shell logic
        if fix_result.exists():
            summary = json.loads(fix_result.read_text()).get("summary", "")
            changed_files_data = json.loads(fix_result.read_text()).get("changed_files", [])

            # Type check
            if isinstance(changed_files_data, list):
                changed_files = ", ".join(changed_files_data)
            else:
                changed_files = str(changed_files_data)

            fix_entry = {
                "round": 2,
                "summary": summary[:200],
                "changed_files": changed_files[:100],
            }

            assert fix_entry["summary"] == "Fixed null pointer exception in auth module"
            assert fix_entry["changed_files"] == "src/auth.py, tests/test_auth.py"

    def test_pr_retry_malformed_response(self, tmp_path: Path) -> None:
        """Simulate PR retry with malformed AI response (changed_files as string)."""
        fix_result = tmp_path / "fix_result.json"
        fix_result.write_text(json.dumps({
            "summary": "Fixed the issue",
            "changed_files": "src/main.py",  # AI returned string instead of array
        }))

        # This should not crash and should handle gracefully
        data = json.loads(fix_result.read_text())
        changed_files_data = data.get("changed_files", [])

        # Simulate jq logic
        if isinstance(changed_files_data, list):
            changed_files = ", ".join(changed_files_data)
        else:
            changed_files = str(changed_files_data) if changed_files_data is not None else ""

        fix_entry = {
            "round": 3,
            "summary": data.get("summary", "")[:200],
            "changed_files": changed_files[:100],
        }

        assert fix_entry["changed_files"] == "src/main.py"

    def test_pr_retry_no_fix_result(self, tmp_path: Path) -> None:
        """Simulate PR retry where fix_result.json doesn't exist (fix failed)."""
        # No fix_result.json created

        fix_result = tmp_path / "fix_result.json"
        # File doesn't exist

        # Simulate the check
        should_create_entry = fix_result.exists()

        assert should_create_entry is False
        # In real workflow, this would skip adding fix_history entry
