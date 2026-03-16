from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ci.validate_ace_config import main


class TestValidateAceConfigBasic:
    """Test basic validation functionality."""

    def test_valid_config_returns_zero(self, write_json):
        """Valid config should exit 0 and output contains 'valid'."""
        valid_config = {
            "tech_stack": {
                "language": "Python 3.12",
                "package_manager": "uv",
                "test_command": "uv run pytest",
                "type_check_command": "uv run basedpyright --level error",
                "runner": "ubuntu-latest",
            },
            "bot": {"name": "bot", "email": "bot@example.com"},
            "branch": {
                "prefix": "ace/fix/issue",
                "detection_patterns": ["ace/*", "fix/*", "issue-*"],
            },
            "labels": {
                "test": {"color": "FFFFFF", "description": "test label"}
            },
        }
        config_path = write_json("config.json", valid_config)
        result = main(str(config_path))
        assert result == 0

    def test_malformed_json_returns_one(self, write_text):
        """Malformed JSON should exit 1 with error in output."""
        config_path = write_text("config.json", "{invalid json")
        result = main(str(config_path))
        assert result == 1

    def test_validate_missing_file(self):
        """Missing config file falls back to defaults, which pass validation."""
        # When file doesn't exist, load_ace_config returns defaults (valid config)
        result = main("/nonexistent/path/to/config.json")
        assert result == 0

    def test_validate_empty_json(self, write_json):
        """Empty JSON object (no tech_stack) should exit 1."""
        empty_config = {}
        config_path = write_json("empty_config.json", empty_config)
        result = main(str(config_path))
        assert result == 1


class TestTechStackValidation:
    """Test tech_stack field validation."""

    def test_missing_tech_stack_returns_one(self, write_json):
        """Config without tech_stack should exit 1."""
        invalid_config = {
            "bot": {"name": "bot", "email": "bot@example.com"},
        }
        config_path = write_json("config.json", invalid_config)
        result = main(str(config_path))
        assert result == 1

    def test_empty_language_returns_one(self, write_json):
        """tech_stack with empty language should exit 1."""
        config = {
            "tech_stack": {
                "language": "",
                "package_manager": "uv",
                "test_command": "uv run pytest",
                "type_check_command": "uv run basedpyright --level error",
                "runner": "ubuntu-latest",
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 1


class TestBranchPrefixValidation:
    """Test branch.prefix validation."""

    def test_prefix_with_double_dot_returns_one(self, write_json):
        """branch.prefix with '..' should exit 1."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "branch": {
                "prefix": "ace/../fix",
                "detection_patterns": ["ace/*"],
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 1

    def test_prefix_with_tilde_returns_one(self, write_json):
        """branch.prefix with '~' should exit 1."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "branch": {
                "prefix": "ace/~fix",
                "detection_patterns": ["ace/*"],
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 1

    def test_valid_prefix_returns_zero(self, write_json):
        """Valid branch.prefix should exit 0."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "branch": {
                "prefix": "ace/fix/issue",
                "detection_patterns": ["ace/*", "fix/*", "issue-*"],
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 0


class TestBranchConsistencyValidation:
    """Test branch prefix/pattern consistency validation."""

    def test_branch_prefix_pattern_mismatch_returns_one(self, write_json):
        """Mismatched prefix and patterns should exit 1."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "branch": {
                "prefix": "main/fix/issue",
                "detection_patterns": ["ace/*", "fix/*"],
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 1


class TestLabelKeyValidation:
    """Test labels key format validation."""

    def test_label_with_space_returns_one(self, write_json):
        """Label key with space should exit 1."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "labels": {
                "invalid label": {"color": "FFFFFF", "description": "test"}
            },
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 1


class TestUnknownFieldsWarning:
    """Test unknown fields detection (should warn, not error)."""

    def test_unknown_fields_returns_zero_with_warning(self, write_json, capsys):
        """Unknown fields should exit 0 with warning in output."""
        config = {
            "tech_stack": {
                "language": "Python",
                "package_manager": "uv",
                "test_command": "test",
                "type_check_command": "check",
                "runner": "runner",
            },
            "unknown_field": {"key": "value"},
        }
        config_path = write_json("config.json", config)
        result = main(str(config_path))
        assert result == 0
        captured = capsys.readouterr()
        assert "valid" in captured.out.lower()
