# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for validate_config module."""

import json
from unittest.mock import call, mock_open, patch

import pytest
from core.rate_limit.validate_config import main


class TestValidateConfig:
    """Test cases for validate_config module."""

    @pytest.fixture
    def valid_config(self):
        """Return valid configuration fixture."""
        return {
            "permissions": {
                "default": {
                    "models": {
                        "anthropic.claude-3-haiku-20240307-v1:0": {"rpm": 100, "tpm": 10000}
                    },
                    "accounts": ["123456789012"],
                }
            },
            "account_limits": {
                "123456789012": {
                    "anthropic.claude-3-haiku-20240307-v1:0": {"rpm": 1000, "tpm": 50000}
                }
            },
        }

    @pytest.fixture
    def valid_schema(self):
        """Return valid schema fixture."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "permissions": {"type": "object"},
                "account_limits": {"type": "object"},
            },
            "required": ["permissions"],
        }

    @patch("sys.argv", ["validate_config.py"])
    @patch("builtins.print")
    def test_main_no_args(self, mock_print):
        """Test main function with no arguments."""
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with("Usage: validate_config.py <config_file>...")

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.open", side_effect=FileNotFoundError())
    @patch("builtins.print")
    def test_main_schema_not_found(self, mock_print, _mock_open_file):
        """Test main function when schema file is not found."""
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with("❌ Error loading schema: ")

    @patch("sys.argv", ["validate_config.py", "nonexistent.json"])
    @patch("builtins.print")
    def test_main_config_file_not_found(self, mock_print, valid_schema):
        """Test main function when config file doesn't exist."""
        schema_content = json.dumps(valid_schema)

        with (
            patch("builtins.open", mock_open(read_data=schema_content)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        expected_calls = [
            call("Rate limit configuration validation failed:"),
            call("  ❌ Config file not found: nonexistent.json"),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_invalid_json(self, mock_print, valid_schema):
        """Test main function with invalid JSON config."""
        schema_content = json.dumps(valid_schema)
        invalid_json = "{ invalid json }"

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=invalid_json)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        mock_print.assert_any_call("Rate limit configuration validation failed:")

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_missing_default_permission(self, mock_print, valid_schema, valid_config):
        """Test main function with missing default permission."""
        schema_content = json.dumps(valid_schema)
        config_without_default = valid_config.copy()
        config_without_default["permissions"] = {
            "custom": {
                "models": {"model1": {"rpm": 100, "tpm": 1000}},
                "accounts": ["123456789012"],
            }
        }
        config_content = json.dumps(config_without_default)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        expected_calls = [
            call("Rate limit configuration validation failed:"),
            call("  ❌ config.json: Missing required 'default' permission"),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_schema_validation_error(self, mock_print, valid_config):
        """Test main function with schema validation error."""
        invalid_schema = {"type": "string"}  # Config should be object, not string
        schema_content = json.dumps(invalid_schema)
        config_content = json.dumps(valid_config)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        mock_print.assert_any_call("Rate limit configuration validation failed:")

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_valid_config(self, mock_print, valid_schema, valid_config):
        """Test main function with valid configuration."""
        schema_content = json.dumps(valid_schema)
        config_content = json.dumps(valid_config)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
        ):
            main()

        mock_print.assert_called_with("✅ All rate limit configurations are valid")

    @patch("sys.argv", ["validate_config.py", "config1.json", "config2.json"])
    @patch("builtins.print")
    def test_main_multiple_configs(self, mock_print, valid_schema, valid_config):
        """Test main function with multiple valid configurations."""
        schema_content = json.dumps(valid_schema)
        config_content = json.dumps(valid_config)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
        ):
            main()

        mock_print.assert_called_with("✅ All rate limit configurations are valid")

    @patch("sys.argv", ["validate_config.py", "config1.json", "config2.json"])
    @patch("builtins.print")
    def test_main_mixed_valid_invalid_configs(self, mock_print, valid_schema, valid_config):
        """Test main function with mix of valid and invalid configurations."""
        schema_content = json.dumps(valid_schema)
        valid_config_content = json.dumps(valid_config)
        invalid_config = valid_config.copy()
        del invalid_config["permissions"]["default"]
        invalid_config_content = json.dumps(invalid_config)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            elif "config1.json" in str(filename):
                return mock_open(read_data=valid_config_content)()
            else:
                return mock_open(read_data=invalid_config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        expected_calls = [
            call("Rate limit configuration validation failed:"),
            call("  ❌ config2.json: Missing required 'default' permission"),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_config_read_error(self, mock_print, valid_schema):
        """Test main function with config file read error."""
        schema_content = json.dumps(valid_schema)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                raise PermissionError("Permission denied")

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        expected_calls = [
            call("Rate limit configuration validation failed:"),
            call("  ❌ Error reading config.json: Permission denied"),
        ]
        mock_print.assert_has_calls(expected_calls)

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_schema_load_json_error(self, mock_print):
        """Test main function with schema JSON decode error."""
        invalid_schema_json = "{ invalid json }"

        with (
            patch("builtins.open", mock_open(read_data=invalid_schema_json)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        mock_print.assert_called_with(
            "❌ Error loading schema: Expecting property name enclosed in double quotes: line 1 column 3 (char 2)"
        )

    @patch("sys.argv", ["validate_config.py", "config.json"])
    @patch("builtins.print")
    def test_main_config_no_permissions(self, mock_print, valid_schema):
        """Test main function with config missing permissions section."""
        schema_content = json.dumps(valid_schema)
        config_no_permissions = {}
        config_content = json.dumps(config_no_permissions)

        def side_effect(filename, *_args, **_kwargs):
            if "schema.json" in str(filename):
                return mock_open(read_data=schema_content)()
            else:
                return mock_open(read_data=config_content)()

        with (
            patch("builtins.open", side_effect=side_effect),
            patch("pathlib.Path.exists", return_value=True),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        expected_calls = [
            call("Rate limit configuration validation failed:"),
            call("  ❌ config.json: 'permissions' is a required property"),
        ]
        mock_print.assert_has_calls(expected_calls)
