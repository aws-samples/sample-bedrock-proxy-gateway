# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for services.bedrock_service module."""

import os
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from services.bedrock_service import AsyncBedrockClient, BedrockService


class TestBedrockService:
    """Test cases for BedrockService class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.mock_logger = Mock()

    @pytest.mark.asyncio
    @patch("services.bedrock_service.jwt.decode")
    async def test_get_authenticated_client_success(self, mock_jwt_decode):
        """Test successful authenticated client creation."""
        mock_jwt_decode.return_value = {"client_id": "test-client"}

        service = BedrockService(self.mock_session, self.mock_logger)

        # Test with no account_id - should return None
        result = await service.get_authenticated_client("test-token", None)
        assert result is None

        # JWT decode should not be called when no account_id provided
        mock_jwt_decode.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_authenticated_client_no_token(self):
        """Test authenticated client creation with no token."""
        service = BedrockService(self.mock_session, self.mock_logger)

        result = await service.get_authenticated_client("")

        assert result is None

    @pytest.mark.asyncio
    @patch("services.bedrock_service.jwt.decode")
    async def test_get_authenticated_client_no_account(self, mock_jwt_decode):
        """Test authenticated client creation with no available account."""
        mock_jwt_decode.return_value = {"client_id": "test-client"}

        service = BedrockService(self.mock_session, self.mock_logger)

        result = await service.get_authenticated_client("test-token", None)

        assert result is None

    @pytest.mark.asyncio
    @patch("services.bedrock_service.jwt.decode")
    async def test_get_authenticated_client_jwt_error(self, mock_jwt_decode):
        """Test authenticated client creation with JWT decode error."""
        mock_jwt_decode.side_effect = Exception("JWT decode failed")

        service = BedrockService(self.mock_session, self.mock_logger)

        # Test with account_id to trigger JWT processing
        result = await service.get_authenticated_client("invalid-token", "123456789012")

        assert result is None
        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    @patch("services.bedrock_service.get_cache")
    async def test_get_credentials_cache_hit(self, mock_get_cache):
        """Test credential retrieval with cache hit."""
        cached_credentials = {
            "AccessKeyId": "cached-key",
            "SecretAccessKey": "cached-secret",
            "SessionToken": "cached-token",
        }
        mock_get_cache.return_value = cached_credentials

        service = BedrockService(self.mock_session, self.mock_logger)

        result = await service._get_credentials(
            "test-key", "123456789012", "test-client", "test-token"
        )

        assert result == cached_credentials
        mock_get_cache.assert_called_once_with("test-key")

    @pytest.mark.asyncio
    @patch("services.bedrock_service.get_cache")
    @patch("services.bedrock_service.set_cache")
    async def test_get_credentials_cache_miss(self, mock_set_cache, mock_get_cache):
        """Test credential retrieval with cache miss and STS call."""
        mock_get_cache.return_value = None  # Cache miss

        # Mock STS client and response
        mock_sts_client = Mock()
        self.mock_session.client.return_value = mock_sts_client

        mock_credentials = {
            "AccessKeyId": "new-key",
            "SecretAccessKey": "new-secret",
            "SessionToken": "new-token",
            "Expiration": datetime.now(UTC),
        }
        mock_sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": mock_credentials
        }

        with patch.dict(os.environ, {"ENVIRONMENT": "test"}):
            service = BedrockService(self.mock_session, self.mock_logger)

            result = await service._get_credentials(
                "test-key", "123456789012", "test-client", "test-token"
            )

        assert result == mock_credentials
        mock_sts_client.assume_role_with_web_identity.assert_called_once()
        mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_async_bedrock_client(self):
        """Test async bedrock client creation."""
        credentials = {
            "AccessKeyId": "test-key",
            "SecretAccessKey": "test-secret",
            "SessionToken": "test-token",
        }

        mock_shared_session = Mock()
        mock_bedrock_client = Mock()

        with patch("services.bedrock_service.boto3.Session") as mock_session_class:
            mock_session_class.return_value = mock_shared_session
            mock_shared_session.client.return_value = mock_bedrock_client

            service = BedrockService(self.mock_session, self.mock_logger)
            result = await service._create_async_bedrock_client(credentials)

            assert result.client == mock_bedrock_client
            mock_session_class.assert_called_once_with(
                aws_access_key_id="test-key",
                aws_secret_access_key="test-secret",
                aws_session_token="test-token",
            )

    @patch("services.bedrock_service.config")
    def test_init_with_vpc_endpoints(self, mock_config):
        """Test BedrockService initialization with VPC endpoints."""
        mock_config.bedrock_runtime_vpc_endpoint_dns = "bedrock.vpc.endpoint"
        mock_config.sts_vpc_endpoint_dns = "sts.vpc.endpoint"
        mock_config.app_hash = "test-suffix"
        mock_config.shared_role_name = "custom-role"
        mock_config.aws_region = "us-west-2"

        service = BedrockService(self.mock_session, self.mock_logger)

        assert service.bedrock_runtime_vpc_endpoint_dns == "bedrock.vpc.endpoint"
        assert service.sts_vpc_endpoint_dns == "sts.vpc.endpoint"
        assert service.sts_role_session_name_suffix == "test-suffix"
        assert service.shared_role_name == "custom-role"
        assert service.aws_region == "us-west-2"

    @pytest.mark.asyncio
    @patch("services.bedrock_service.get_cache")
    async def test_get_credentials_sts_error(self, mock_get_cache):
        """Test credential retrieval with STS error."""
        mock_get_cache.return_value = None  # Cache miss

        # Mock STS client that raises an exception
        mock_sts_client = Mock()
        mock_sts_client.assume_role_with_web_identity.side_effect = Exception("STS Error")
        self.mock_session.client.return_value = mock_sts_client

        service = BedrockService(self.mock_session, self.mock_logger)

        with pytest.raises(Exception, match="STS Error"):
            await service._get_credentials("test-key", "123456789012", "test-client", "test-token")

    @pytest.mark.asyncio
    @patch("services.bedrock_service.config")
    @patch("services.bedrock_service.get_cache")
    @patch("services.bedrock_service.set_cache")
    async def test_get_credentials_with_role_session_suffix(
        self, _mock_set_cache, mock_get_cache, mock_config
    ):
        """Test credential retrieval with role session name suffix."""
        mock_get_cache.return_value = None
        mock_config.environment = "production"
        mock_config.app_hash = "gateway-instance-1"
        mock_config.shared_role_name = "shared-account-role"
        mock_config.aws_region = "us-east-1"
        mock_config.bedrock_runtime_vpc_endpoint_dns = ""
        mock_config.sts_vpc_endpoint_dns = ""

        mock_sts_client = Mock()
        self.mock_session.client.return_value = mock_sts_client

        mock_credentials = {
            "AccessKeyId": "key",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
            "Expiration": datetime.now(UTC),
        }
        mock_sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": mock_credentials
        }

        service = BedrockService(self.mock_session, self.mock_logger)

        await service._get_credentials("test-key", "123456789012", "test-client", "test-token")

        # Verify role session name includes suffix
        mock_sts_client.assume_role_with_web_identity.assert_called_once()
        call_args = mock_sts_client.assume_role_with_web_identity.call_args
        expected_session_name = "production_test-client_gateway-instance-1"
        assert call_args.kwargs["RoleSessionName"] == expected_session_name

    @pytest.mark.asyncio
    @patch("services.bedrock_service.config")
    async def test_create_async_bedrock_client_with_vpc_endpoint(self, mock_config):
        """Test async bedrock client creation with VPC endpoint."""
        mock_config.bedrock_runtime_vpc_endpoint_dns = "bedrock.vpc.endpoint"
        mock_config.shared_role_name = "shared-account-role"
        mock_config.aws_region = "us-east-1"
        mock_config.sts_vpc_endpoint_dns = ""
        mock_config.app_hash = ""

        credentials = {
            "AccessKeyId": "test-key",
            "SecretAccessKey": "test-secret",
            "SessionToken": "test-token",
        }

        mock_shared_session = Mock()
        mock_bedrock_client = Mock()

        with patch("services.bedrock_service.boto3.Session") as mock_session_class:
            mock_session_class.return_value = mock_shared_session
            mock_shared_session.client.return_value = mock_bedrock_client

            service = BedrockService(self.mock_session, self.mock_logger)
            await service._create_async_bedrock_client(credentials)

            # Verify VPC endpoint is used
            mock_shared_session.client.assert_called_once_with(
                "bedrock-runtime",
                region_name=service.aws_region,
                endpoint_url="https://bedrock.vpc.endpoint",
            )

    @pytest.mark.asyncio
    @patch("services.bedrock_service.jwt.decode")
    async def test_get_authenticated_client_credentials_failure(self, mock_jwt_decode):
        """Test authenticated client creation when credential retrieval fails."""
        mock_jwt_decode.return_value = {"client_id": "test-client"}

        service = BedrockService(self.mock_session, self.mock_logger)

        result = await service.get_authenticated_client("test-token", None)

        assert result is None

    @pytest.mark.asyncio
    @patch("services.bedrock_service.jwt.decode")
    async def test_get_authenticated_client_missing_client_id(self, mock_jwt_decode):
        """Test authenticated client creation with missing client_id in JWT."""
        mock_jwt_decode.return_value = {}  # No client_id

        service = BedrockService(self.mock_session, self.mock_logger)

        result = await service.get_authenticated_client("test-token", None)

        # Should return None since no account mapping is available
        assert result is None

    @pytest.mark.asyncio
    @patch("services.bedrock_service.config")
    @patch("services.bedrock_service.get_cache")
    @patch("services.bedrock_service.set_cache")
    async def test_get_credentials_with_sts_vpc_endpoint(
        self, _mock_set_cache, mock_get_cache, mock_config
    ):
        """Test credential retrieval with STS VPC endpoint."""
        mock_get_cache.return_value = None
        mock_config.sts_vpc_endpoint_dns = "sts.vpc.endpoint"
        mock_config.shared_role_name = "shared-account-role"
        mock_config.aws_region = "us-east-1"
        mock_config.bedrock_runtime_vpc_endpoint_dns = ""
        mock_config.app_hash = ""
        mock_config.environment = "dev"

        mock_sts_client = Mock()
        self.mock_session.client.return_value = mock_sts_client

        mock_credentials = {
            "AccessKeyId": "key",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
            "Expiration": datetime.now(UTC),
        }
        mock_sts_client.assume_role_with_web_identity.return_value = {
            "Credentials": mock_credentials
        }

        service = BedrockService(self.mock_session, self.mock_logger)

        await service._get_credentials("test-key", "123456789012", "test-client", "test-token")

        # Verify STS client created with VPC endpoint
        self.mock_session.client.assert_called_once_with(
            "sts",
            region_name=service.aws_region,
            endpoint_url="https://sts.vpc.endpoint",
        )


class TestAsyncBedrockClient:
    """Test cases for AsyncBedrockClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = Mock()
        self.async_client = AsyncBedrockClient(self.mock_client)

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager functionality."""
        async with self.async_client as client:
            assert client == self.async_client
            assert self.async_client.loop is not None

    @pytest.mark.asyncio
    async def test_converse_method(self):
        """Test async converse method."""
        self.mock_client.converse.return_value = {"response": "test"}

        async with self.async_client as client:
            result = await client.converse(modelId="test-model")

        assert result == {"response": "test"}
        self.mock_client.converse.assert_called_once_with(modelId="test-model")

    @pytest.mark.asyncio
    async def test_invoke_model_method(self):
        """Test async invoke_model method."""
        self.mock_client.invoke_model.return_value = {"body": "test"}

        async with self.async_client as client:
            result = await client.invoke_model(modelId="test-model")

        assert result == {"body": "test"}
        self.mock_client.invoke_model.assert_called_once_with(modelId="test-model")

    @pytest.mark.asyncio
    async def test_converse_stream_method(self):
        """Test async converse_stream method."""
        self.mock_client.converse_stream.return_value = {"stream": "test"}

        async with self.async_client as client:
            result = await client.converse_stream(modelId="test-model")

        assert result == {"stream": "test"}
        self.mock_client.converse_stream.assert_called_once_with(modelId="test-model")

    @pytest.mark.asyncio
    async def test_invoke_model_with_response_stream_method(self):
        """Test async invoke_model_with_response_stream method."""
        self.mock_client.invoke_model_with_response_stream.return_value = {"body": "stream"}

        async with self.async_client as client:
            result = await client.invoke_model_with_response_stream(modelId="test-model")

        assert result == {"body": "stream"}
        self.mock_client.invoke_model_with_response_stream.assert_called_once_with(
            modelId="test-model"
        )
