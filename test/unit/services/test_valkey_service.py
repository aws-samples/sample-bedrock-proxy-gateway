# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for services.valkey_service module."""

from unittest.mock import AsyncMock, patch

import pytest
import services.valkey_service


class TestValkeyService:
    """Test cases for Valkey service."""

    def setup_method(self):
        """Reset global client before each test."""
        services.valkey_service._client = None

    @pytest.mark.asyncio
    @patch("services.valkey_service.GlideClusterClient.create")
    async def test_get_client_iam_auth(self, mock_create):
        """Test create_valkey_client with IAM authentication."""
        mock_client = AsyncMock()
        mock_create.return_value = mock_client

        with patch("services.valkey_service.config") as mock_config:
            mock_config.elasticache_use_iam = True
            mock_config.elasticache_cluster_name = "test-cluster"
            mock_config.elasticache_username = "test-user"
            mock_config.aws_region = "us-east-1"
            mock_config.valkey_url = "async+rediss://localhost:6379"
            mock_config.valkey_ssl = True

            client = await services.valkey_service.create_valkey_client()

            assert client == mock_client
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.valkey_service.GlideClusterClient.create")
    async def test_get_client_password_auth(self, mock_create):
        """Test create_valkey_client with password authentication."""
        mock_client = AsyncMock()
        mock_create.return_value = mock_client

        with patch("services.valkey_service.config") as mock_config:
            mock_config.elasticache_use_iam = False
            mock_config.valkey_url = "async+rediss://user:pass@localhost:6379"
            mock_config.valkey_ssl = True

            client = await services.valkey_service.create_valkey_client()

            assert client == mock_client
            mock_create.assert_called_once()
