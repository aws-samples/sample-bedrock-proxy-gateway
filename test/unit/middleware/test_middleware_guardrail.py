# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for middleware.guardrail module."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from middleware.guardrail import GuardrailMiddleware
from services.guardrail_service import GuardrailService


class TestGuardrailMiddleware:
    """Test cases for GuardrailMiddleware class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = Mock()
        self.mock_guardrail_service = Mock(spec=GuardrailService)
        self.middleware = GuardrailMiddleware(self.app, self.mock_guardrail_service)

    @pytest.mark.asyncio
    async def test_dispatch_non_bedrock_endpoint(self):
        """Test middleware bypass for non-Bedrock endpoints."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/health"
        request.url = mock_url
        request.state = Mock()

        # Ensure the state doesn't have guardrail_config initially
        if hasattr(request.state, "guardrail_config"):
            delattr(request.state, "guardrail_config")

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await self.middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)
        # For non-Bedrock endpoints, guardrail_config should not be set
        assert not hasattr(request.state, "guardrail_config")

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    @patch("middleware.guardrail.guardrail_span")
    async def test_dispatch_bedrock_endpoint_success(self, mock_span, mock_client_context):
        """Test successful guardrail config extraction for Bedrock endpoint."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/converse"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "claude-v2", "account-456", 1000, "converse")

        mock_client_context.get.return_value = "client-123"
        mock_span.return_value.__aenter__ = AsyncMock()
        mock_span.return_value.__aexit__ = AsyncMock()

        # Mock successful guardrail config
        mock_config = {"guardrailIdentifier": "gr-123", "guardrailVersion": "1"}
        with patch.object(
            self.middleware, "_extract_guardrail_config", return_value=mock_config
        ) as mock_extract:
            call_next = AsyncMock()
            expected_response = Mock()
            call_next.return_value = expected_response

            result = await self.middleware.dispatch(request, call_next)

            assert result == expected_response
            assert request.state.guardrail_config == mock_config
            mock_extract.assert_called_once_with(request)
            call_next.assert_called_once_with(request)
            mock_span.assert_called_once()

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    @patch("middleware.guardrail.guardrail_span")
    async def test_dispatch_bedrock_endpoint_http_exception(self, mock_span, mock_client_context):
        """Test HTTP exception propagation during guardrail config extraction."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/converse"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "claude-v2", "account-456", 1000, "converse")

        mock_client_context.get.return_value = "client-123"

        # Create a proper async context manager mock
        class MockAsyncContextManager:
            async def __aenter__(self):
                return Mock()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None

        mock_span.return_value = MockAsyncContextManager()

        # Mock HTTP exception
        with patch.object(
            self.middleware,
            "_extract_guardrail_config",
            side_effect=HTTPException(status_code=400, detail="Guardrail not found"),
        ):
            call_next = AsyncMock()

            with pytest.raises(HTTPException) as exc_info:
                await self.middleware.dispatch(request, call_next)

            assert exc_info.value.status_code == 400
            call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    @patch("middleware.guardrail.logger")
    async def test_dispatch_bedrock_endpoint_general_exception(
        self, mock_logger, mock_client_context
    ):
        """Test general exception handling during guardrail config extraction."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/converse"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "claude-v2", "account-456", 1000, "converse")

        mock_client_context.get.return_value = "client-123"

        # Mock general exception
        with patch.object(
            self.middleware,
            "_extract_guardrail_config",
            side_effect=Exception("Unexpected error"),
        ):
            call_next = AsyncMock()
            expected_response = Mock()
            call_next.return_value = expected_response

            result = await self.middleware.dispatch(request, call_next)

            assert result == expected_response
            assert request.state.guardrail_config is None
            mock_logger.error.assert_called_once()
            call_next.assert_called_once_with(request)

    def test_is_bedrock_endpoint_converse(self):
        """Test Bedrock endpoint detection for converse APIs."""
        assert self.middleware._is_bedrock_endpoint("/model/claude-v2/converse")
        assert self.middleware._is_bedrock_endpoint("/model/titan/converse-stream")

    def test_is_bedrock_endpoint_invoke(self):
        """Test Bedrock endpoint detection for invoke APIs."""
        assert self.middleware._is_bedrock_endpoint("/model/claude-v2/invoke")
        assert self.middleware._is_bedrock_endpoint("/model/titan/invoke-with-response-stream")

    def test_is_bedrock_endpoint_guardrail(self):
        """Test Bedrock endpoint detection for guardrail APIs."""
        assert self.middleware._is_bedrock_endpoint("/guardrail/baseline/apply")

    def test_is_bedrock_endpoint_non_bedrock(self):
        """Test Bedrock endpoint detection for non-Bedrock paths."""
        assert not self.middleware._is_bedrock_endpoint("/health")
        assert not self.middleware._is_bedrock_endpoint("/docs")
        assert not self.middleware._is_bedrock_endpoint("/model/claude-v2")

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    async def test_extract_guardrail_config_invoke_path(self, mock_client_context):
        """Test guardrail config extraction for invoke endpoints."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/invoke"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "claude-v2", "account-456", 1000, "invoke")

        mock_client_context.get.return_value = "client-123"

        with patch.object(
            self.middleware, "_get_guardrail_from_headers", return_value={"test": "config"}
        ) as mock_headers:
            result = await self.middleware._extract_guardrail_config(request)

            assert result == {"test": "config"}
            mock_headers.assert_called_once_with(request, "account-456", "client-123")

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    async def test_extract_guardrail_config_converse_path(self, mock_client_context):
        """Test guardrail config extraction for converse endpoints."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/converse"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "claude-v2", "account-456", 1000, "converse")

        mock_client_context.get.return_value = "client-123"

        with patch.object(
            self.middleware, "_get_guardrail_from_body", return_value={"test": "config"}
        ) as mock_body:
            result = await self.middleware._extract_guardrail_config(request)

            assert result == {"test": "config"}
            mock_body.assert_called_once_with(request, "account-456", "client-123")

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    async def test_extract_guardrail_config_apply_path(self, mock_client_context):
        """Test guardrail config extraction for apply guardrail endpoints."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/guardrail/baseline/apply"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = ("client-123", "model", "account-456", 1000, "apply")

        mock_client_context.get.return_value = "client-123"

        with patch.object(
            self.middleware, "_get_guardrail_from_path", return_value={"test": "config"}
        ) as mock_path:
            result = await self.middleware._extract_guardrail_config(request)

            assert result == {"test": "config"}
            mock_path.assert_called_once_with(request, "account-456")

    @pytest.mark.asyncio
    @patch("middleware.guardrail.client_id_context")
    @patch("middleware.guardrail.logger")
    async def test_extract_guardrail_config_no_shared_account(
        self, mock_logger, mock_client_context
    ):
        """Test guardrail config extraction with missing shared account ID."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude-v2/converse"
        request.url = mock_url
        request.state = Mock()
        request.state.rate_ctx = None

        mock_client_context.get.return_value = "client-123"

        result = await self.middleware._extract_guardrail_config(request)

        assert result is None
        mock_logger.warning.assert_called_once_with(
            "No shared account ID found in rate limiting context"
        )

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_applied")
    async def test_get_guardrail_from_headers_with_valid_id(self, mock_record_applied):
        """Test guardrail extraction from headers with valid logical ID."""
        request = Mock(spec=Request)
        request.headers.get.return_value = "baseline-security"

        mock_config = {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "enabled",
        }
        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=mock_config)

        result = await self.middleware._get_guardrail_from_headers(
            request, "account-456", "client-123"
        )

        assert result == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "ENABLED",
        }
        self.mock_guardrail_service.get_guardrail_config.assert_called_once_with(
            "baseline-security", "account-456"
        )
        mock_record_applied.assert_called_once_with(
            "client-123", "baseline-security", "account-456", "invoke"
        )

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_not_found")
    async def test_get_guardrail_from_headers_not_found(self, mock_record_not_found):
        """Test guardrail extraction from headers when guardrail not found."""
        request = Mock(spec=Request)
        request.headers.get.return_value = "nonexistent-guardrail"

        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware._get_guardrail_from_headers(request, "account-456", "client-123")

        assert exc_info.value.status_code == 400
        assert "not found for account" in exc_info.value.detail
        mock_record_not_found.assert_called_once_with(
            "client-123", "nonexistent-guardrail", "account-456"
        )

    @pytest.mark.asyncio
    async def test_get_guardrail_from_headers_no_guardrail(self):
        """Test guardrail extraction from headers with no guardrail specified."""
        request = Mock(spec=Request)
        request.headers.get.return_value = None

        result = await self.middleware._get_guardrail_from_headers(
            request, "account-456", "client-123"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guardrail_from_headers_invalid_id_format(self):
        """Test guardrail extraction from headers with invalid ID format."""
        request = Mock(spec=Request)
        request.headers.get.return_value = "invalid@id!"

        result = await self.middleware._get_guardrail_from_headers(
            request, "account-456", "client-123"
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_applied")
    async def test_get_guardrail_from_body_with_valid_id(self, mock_record_applied):
        """Test guardrail extraction from body with valid logical ID."""
        request = Mock(spec=Request)
        body_data = {
            "messages": [{"role": "user", "content": "test"}],
            "guardrailConfig": {"guardrailIdentifier": "baseline-security"},
        }
        request.body = AsyncMock(return_value=json.dumps(body_data).encode())
        request.state = Mock()

        mock_config = {"guardrailIdentifier": "gr-123", "guardrailVersion": "1"}
        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=mock_config)

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        assert result == mock_config
        assert hasattr(request.state, "modified_body")
        assert request.state.modified_body["guardrailConfig"] == mock_config
        mock_record_applied.assert_called_once_with(
            "client-123", "baseline-security", "account-456", "converse"
        )

    @pytest.mark.asyncio
    @patch("middleware.guardrail.logger")
    async def test_get_guardrail_from_body_not_found(self, mock_logger):
        """Test guardrail extraction from body when guardrail not found."""
        request = Mock(spec=Request)
        body_data = {
            "messages": [{"role": "user", "content": "test"}],
            "guardrailConfig": {"guardrailIdentifier": "nonexistent"},
        }
        request.body = AsyncMock(return_value=json.dumps(body_data).encode())
        request.state = Mock()

        # The guardrail is not found, HTTPException is raised but caught and logged
        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=None)

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        # The method returns None because the HTTPException is caught
        assert result is None
        # Verify that an error was logged
        mock_logger.error.assert_called_once()
        # Verify that get_guardrail_config was called
        self.mock_guardrail_service.get_guardrail_config.assert_called_once_with(
            "nonexistent", "account-456"
        )

    @pytest.mark.asyncio
    async def test_get_guardrail_from_body_no_guardrail(self):
        """Test guardrail extraction from body with no guardrail specified."""
        request = Mock(spec=Request)
        body_data = {"messages": [{"role": "user", "content": "test"}]}
        request.body = AsyncMock(return_value=json.dumps(body_data).encode())
        request.state = Mock()

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guardrail_from_body_empty_body(self):
        """Test guardrail extraction from empty body."""
        request = Mock(spec=Request)
        request.body = AsyncMock(return_value=b"")

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guardrail_from_body_invalid_json(self):
        """Test guardrail extraction from body with invalid JSON."""
        request = Mock(spec=Request)
        request.body = AsyncMock(return_value=b"invalid json")

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        assert result is None

    @pytest.mark.asyncio
    @patch("middleware.guardrail.logger")
    async def test_get_guardrail_from_body_exception(self, mock_logger):
        """Test guardrail extraction from body with exception."""
        request = Mock(spec=Request)
        request.body = AsyncMock(side_effect=Exception("Body read error"))

        result = await self.middleware._get_guardrail_from_body(
            request, "account-456", "client-123"
        )

        assert result is None
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_applied")
    async def test_get_guardrail_from_path_valid_id(self, mock_record_applied):
        """Test guardrail extraction from path with valid logical ID."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/guardrail/baseline-security/apply"
        request.url = mock_url
        request.state = Mock()

        mock_config = {"guardrailIdentifier": "gr-123", "guardrailVersion": "1"}
        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=mock_config)

        result = await self.middleware._get_guardrail_from_path(request, "account-456")

        assert result == mock_config
        assert hasattr(request.state, "resolved_guardrail")
        assert request.state.resolved_guardrail == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
        }
        mock_record_applied.assert_called_once_with(
            "unknown", "baseline-security", "account-456", "apply"
        )

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_not_found")
    async def test_get_guardrail_from_path_not_found(self, mock_record_not_found):
        """Test guardrail extraction from path when guardrail not found."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/guardrail/nonexistent/apply"
        request.url = mock_url

        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware._get_guardrail_from_path(request, "account-456")

        assert exc_info.value.status_code == 400
        assert "not found for account" in exc_info.value.detail
        mock_record_not_found.assert_called_once_with("unknown", "nonexistent", "account-456")

    @pytest.mark.asyncio
    async def test_get_guardrail_from_path_invalid_id_format(self):
        """Test guardrail extraction from path with invalid ID format."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/guardrail/invalid@id!/apply"
        request.url = mock_url

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware._get_guardrail_from_path(request, "account-456")

        assert exc_info.value.status_code == 400
        assert "Invalid guardrail logical ID" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("middleware.guardrail.record_guardrail_not_found")
    async def test_get_guardrail_from_path_malformed_path(self, mock_record_not_found):
        """Test guardrail extraction from path where 'apply' is treated as guardrail ID."""
        request = Mock(spec=Request)
        # Create a proper mock for url.path
        mock_url = Mock()
        mock_url.path = "/guardrail/apply"  # "apply" will be treated as guardrail ID
        request.url = mock_url
        request.state = Mock()

        # Mock the service to return None (guardrail "apply" not found)
        self.mock_guardrail_service.get_guardrail_config = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware._get_guardrail_from_path(request, "account-456")

        assert exc_info.value.status_code == 400
        assert "not found for account" in exc_info.value.detail
        self.mock_guardrail_service.get_guardrail_config.assert_called_once_with(
            "apply", "account-456"
        )
        mock_record_not_found.assert_called_once_with("unknown", "apply", "account-456")

    @pytest.mark.asyncio
    async def test_get_guardrail_from_path_no_guardrail_segment(self):
        """Test guardrail extraction from path without guardrail segment."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/model/claude/invoke"
        request.url = mock_url

        result = await self.middleware._get_guardrail_from_path(request, "account-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_guardrail_from_path_truly_malformed(self):
        """Test guardrail extraction from truly malformed path with empty ID after guardrail."""
        request = Mock(spec=Request)
        mock_url = Mock()
        mock_url.path = "/guardrail/"  # Ends with slash, empty ID
        request.url = mock_url

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware._get_guardrail_from_path(request, "account-456")

        assert exc_info.value.status_code == 400
        assert "Invalid guardrail logical ID" in exc_info.value.detail
