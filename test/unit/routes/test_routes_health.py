# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for routes.health module."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import Response
from routes.health import _create_valkey_response, health, valkey_health


class TestHealthRoute:
    """Test cases for health check endpoint."""

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_health_endpoint_success(self, mock_config):
        """Test successful health check response."""
        mock_config.environment = "test"
        mock_config.otel_service_name = "bedrock-proxy-gateway"

        response = await health()

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.media_type == "application/json"

        # Parse response content
        content = json.loads(response.body)
        assert content["status"] == "healthy"
        assert content["env"] == "test"
        assert content["service"] == "bedrock-proxy-gateway"

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_health_endpoint_default_values(self, mock_config):
        """Test health check with default environment values."""
        mock_config.environment = "unknown"
        mock_config.otel_service_name = "unknown"

        response = await health()

        assert isinstance(response, Response)
        assert response.status_code == 200

        content = json.loads(response.body)
        assert content["status"] == "healthy"
        assert content["env"] == "unknown"
        assert content["service"] == "unknown"

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_health_endpoint_missing_env_vars(self, mock_config):
        """Test health check when environment variables are missing."""
        mock_config.environment = "unknown"
        mock_config.otel_service_name = "unknown"

        response = await health()

        assert isinstance(response, Response)
        assert response.status_code == 200

        content = json.loads(response.body)
        assert content["status"] == "healthy"
        assert content["env"] == "unknown"
        assert content["service"] == "unknown"

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_health_endpoint_production_env(self, mock_config):
        """Test health check in production environment."""
        mock_config.environment = "prod"
        mock_config.otel_service_name = "bedrock-proxy-gateway-prod"

        response = await health()

        content = json.loads(response.body)
        assert content["env"] == "prod"
        assert content["service"] == "bedrock-proxy-gateway-prod"

    @pytest.mark.asyncio
    async def test_health_endpoint_response_format(self):
        """Test health check response format and structure."""
        response = await health()

        # Verify response is properly formatted JSON
        content = json.loads(response.body)

        # Check required fields exist
        required_fields = ["status", "env", "service"]
        for field in required_fields:
            assert field in content

        # Check field types
        assert isinstance(content["status"], str)
        assert isinstance(content["env"], str)
        assert isinstance(content["service"], str)

        # Check status value
        assert content["status"] == "healthy"


class TestCreateValkeyResponse:
    """Test cases for _create_valkey_response helper function."""

    def test_create_valkey_response_healthy(self):
        """Test creating healthy Valkey response."""
        response = _create_valkey_response("healthy", "Connection successful")

        assert isinstance(response, Response)
        assert response.status_code == 200
        assert response.media_type == "application/json"

        content = json.loads(response.body)
        assert content["status"] == "healthy"
        assert content["service"] == "valkey"
        assert content["message"] == "Connection successful"

    def test_create_valkey_response_unhealthy(self):
        """Test creating unhealthy Valkey response."""
        response = _create_valkey_response("unhealthy", "Connection failed")

        assert isinstance(response, Response)
        assert response.status_code == 503
        assert response.media_type == "application/json"

        content = json.loads(response.body)
        assert content["status"] == "unhealthy"
        assert content["service"] == "valkey"
        assert content["message"] == "Connection failed"


class TestValkeyHealthRoute:
    """Test cases for Valkey health check endpoint."""

    def setup_method(self):
        """Reset global client before each test."""
        import services.valkey_service

        services.valkey_service._client = None

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_success(self, mock_config):
        """Test successful Valkey health check."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.return_value = b"PONG"

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert isinstance(response, Response)
            assert response.status_code == 200
            content = json.loads(response.body)
            assert content["status"] == "healthy"
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_check_returns_false(self, mock_config):
        """Test Valkey health check when check returns False."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.return_value = False

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 503
            content = json.loads(response.body)
            assert content["status"] == "unhealthy"

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_timeout_error(self, mock_config):
        """Test Valkey health check with timeout error."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.side_effect = TimeoutError()

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 503
            content = json.loads(response.body)
            assert content["message"] == "Valkey connection timed out after 5 seconds"

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_connection_error(self, mock_config):
        """Test Valkey health check with connection error."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.side_effect = ConnectionError("Connection refused")

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 503
            content = json.loads(response.body)
            assert "Connection refused" in content["message"]

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_generic_exception(self, mock_config):
        """Test Valkey health check with generic exception."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Unexpected error")

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 503
            content = json.loads(response.body)
            assert "Unexpected error" in content["message"]

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_default_url(self, mock_config):
        """Test Valkey health check with default URL."""
        mock_config.valkey_url = "redis://localhost:6379"
        mock_client = AsyncMock()
        mock_client.ping.return_value = b"PONG"

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 200

    @pytest.mark.asyncio
    @patch("routes.health.config")
    async def test_valkey_health_custom_url(self, mock_config):
        """Test Valkey health check with custom URL."""
        mock_config.valkey_url = "redis://custom-host:6380"
        mock_client = AsyncMock()
        mock_client.ping.return_value = b"PONG"

        async def mock_create():
            return mock_client

        with patch("routes.health.create_valkey_client", side_effect=mock_create):
            response = await valkey_health()
            assert response.status_code == 200
