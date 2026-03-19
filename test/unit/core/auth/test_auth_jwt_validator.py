# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for auth.jwt_validator module."""

import time
from unittest.mock import Mock, patch

import jwt
import pytest
from core.auth.jwt_validator import validate_jwt_claims, validate_jwt_token


class TestJWTValidator:
    """Test cases for JWT validation functions."""

    @patch("core.auth.jwt_validator._get_jwks_client")
    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_token_success(self, mock_config, mock_get_client):
        """Test successful JWT token validation."""
        mock_config.jwks_url = "https://test.com/jwks"
        mock_config.jwt_audience = "test-audience"
        mock_config.oauth_issuer = "https://test.com"

        mock_signing_key = Mock()
        mock_signing_key.key = Mock()
        mock_client = Mock()
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_get_client.return_value = mock_client

        test_claims = {"sub": "test", "aud": "test-audience"}

        with patch("jwt.decode") as mock_decode:
            mock_decode.return_value = test_claims

            result = validate_jwt_token("test.jwt.token")

            assert result == test_claims
            mock_decode.assert_called_once_with(
                "test.jwt.token",
                key=mock_signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                audience="test-audience",
                issuer="https://test.com",
                options={
                    "verify_aud": True,
                    "verify_iss": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                },
            )

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_token_no_key(self, mock_config):
        """Test JWT validation when no key is available."""
        mock_config.jwks_url = ""

        with pytest.raises(ValueError, match="JWKS URL not configured"):
            validate_jwt_token("test.jwt.token")

    @patch("core.auth.jwt_validator._get_jwks_client")
    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_token_expired(self, mock_config, mock_get_client):
        """Test JWT validation with expired token."""
        mock_config.jwks_url = "https://test.com/jwks"
        mock_config.jwt_audience = "test-audience"

        mock_signing_key = Mock()
        mock_signing_key.key = Mock()
        mock_client = Mock()
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_get_client.return_value = mock_client

        with patch("jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

            with pytest.raises(ValueError, match="Token has expired"):
                validate_jwt_token("test.jwt.token")

    @patch("core.auth.jwt_validator._get_jwks_client")
    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_token_invalid_audience(self, mock_config, mock_get_client):
        """Test JWT validation with invalid audience."""
        mock_config.jwks_url = "https://test.com/jwks"
        mock_config.jwt_audience = "test-audience"

        mock_signing_key = Mock()
        mock_signing_key.key = Mock()
        mock_client = Mock()
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_get_client.return_value = mock_client

        with patch("jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidAudienceError("Invalid audience")

            with pytest.raises(ValueError, match="Invalid audience"):
                validate_jwt_token("test.jwt.token")

    @patch("core.auth.jwt_validator._get_jwks_client")
    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_token_invalid_token(self, mock_config, mock_get_client):
        """Test JWT validation with invalid token."""
        mock_config.jwks_url = "https://test.com/jwks"
        mock_config.jwt_audience = "test-audience"

        mock_signing_key = Mock()
        mock_signing_key.key = Mock()
        mock_client = Mock()
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key
        mock_get_client.return_value = mock_client

        with patch("jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidTokenError("Invalid token")

            with pytest.raises(ValueError, match="Invalid token"):
                validate_jwt_token("test.jwt.token")

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_success(self, mock_config):
        """Test successful JWT claims validation."""
        mock_config.allowed_scopes = ["bedrockproxygateway:invoke"]

        current_time = time.time()
        claims = {
            "client_id": "test-client",
            "scope": "bedrockproxygateway:invoke",
            "nbf": current_time - 100,
            "exp": current_time + 3600,
            "org": "test-org",
        }

        result = validate_jwt_claims(claims)

        assert result == {
            "client_id": "test-client",
            "scope": "bedrockproxygateway:invoke",
            "orgId": "test-org",
        }

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_missing_client_id(self, _mock_config):
        """Test claims validation with missing client_id."""
        claims = {"scope": "bedrockproxygateway:invoke"}

        with pytest.raises(ValueError, match="Missing required claims"):
            validate_jwt_claims(claims)

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_missing_scope(self, _mock_config):
        """Test claims validation with missing scope."""
        claims = {"client_id": "test-client"}

        with pytest.raises(ValueError, match="Missing required claim: scope"):
            validate_jwt_claims(claims)

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_invalid_scope(self, mock_config):
        """Test claims validation with invalid scope."""
        mock_config.allowed_scopes = ["bedrockproxygateway:invoke"]

        claims = {"client_id": "test-client", "scope": "invalid:scope"}

        with pytest.raises(ValueError, match="Invalid scope"):
            validate_jwt_claims(claims)

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_invalid_time(self, mock_config):
        """Test claims validation with invalid time."""
        mock_config.allowed_scopes = ["bedrockproxygateway:invoke"]

        current_time = time.time()
        claims = {
            "client_id": "test-client",
            "scope": "bedrockproxygateway:invoke",
            "nbf": current_time + 100,  # Future not-before
            "exp": current_time + 3600,
        }

        with pytest.raises(ValueError, match="Token not valid for current time"):
            validate_jwt_claims(claims)

    @patch("core.auth.jwt_validator.config")
    def test_validate_jwt_claims_fallback_org_id(self, mock_config):
        """Test claims validation with fallback org_id."""
        mock_config.allowed_scopes = ["bedrockproxygateway:invoke"]

        current_time = time.time()
        claims = {
            "client_id": "test-client",
            "scope": "bedrockproxygateway:invoke",
            "nbf": current_time - 100,
            "exp": current_time + 3600,
            # No org claim
        }

        result = validate_jwt_claims(claims)

        assert result == {
            "client_id": "test-client",
            "scope": "bedrockproxygateway:invoke",
            "orgId": "test-client",
        }
