# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for config module."""

from config import Config


class TestConfig:
    """Test cases for Config class.

    Tests configuration loading and environment-specific settings
    for JWT validation and API configuration.
    """

    def test_config_dev_environment(self, monkeypatch):
        """Test config for dev environment.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.setenv("OAUTH_JWKS_URL", "https://test-oauth.com/.well-known/jwks.json")
        config = Config()

        assert config.environment == "dev"
        assert config.jwks_url == "https://test-oauth.com/.well-known/jwks.json"
        assert config.jwt_audience == "bedrockproxygateway"
        assert config.allowed_scopes == [
            "bedrockproxygateway:read",
            "bedrockproxygateway:invoke",
            "bedrockproxygateway:admin",
        ]

    def test_config_test_environment(self, monkeypatch):
        """Test config for test environment.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("OAUTH_JWKS_URL", "https://test-oauth.com/.well-known/jwks.json")
        config = Config()

        assert config.environment == "test"
        assert config.jwks_url == "https://test-oauth.com/.well-known/jwks.json"
        assert config.jwt_audience == "bedrockproxygateway"
        assert config.allowed_scopes == [
            "bedrockproxygateway:read",
            "bedrockproxygateway:invoke",
            "bedrockproxygateway:admin",
        ]

    def test_config_default_environment(self, monkeypatch):
        """Test config with default environment.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("OAUTH_JWKS_URL", raising=False)
        config = Config()

        assert config.environment == "dev"
        assert config.jwks_url == ""
        assert config.jwt_audience == "bedrockproxygateway"
        assert config.allowed_scopes == [
            "bedrockproxygateway:read",
            "bedrockproxygateway:invoke",
            "bedrockproxygateway:admin",
        ]

    def test_rate_limiting_disabled_for_dev_qa(self, monkeypatch):
        """Test rate limiting is disabled for dev environment.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        # Test dev environment
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.delenv("RATE_LIMITING_ENABLED", raising=False)
        config = Config()
        assert config.rate_limiting_enabled is False

    def test_rate_limiting_enabled_for_other_environments(self, monkeypatch):
        """Test rate limiting is enabled for test environment.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.delenv("RATE_LIMITING_ENABLED", raising=False)
        config = Config()
        assert config.rate_limiting_enabled is True

    def test_rate_limiting_override_with_env_var(self, monkeypatch):
        """Test rate limiting can be overridden with environment variable.

        Args:
        ----
            monkeypatch: Pytest fixture for environment variable patching.
        """
        # Override disabled default in dev environment
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.setenv("RATE_LIMITING_ENABLED", "true")
        config = Config()
        assert config.rate_limiting_enabled is True

        # Override enabled default in test environment
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("RATE_LIMITING_ENABLED", "false")
        config = Config()
        assert config.rate_limiting_enabled is False
