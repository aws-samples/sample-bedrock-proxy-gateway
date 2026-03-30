# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for middleware.auth module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from middleware.auth import AuthMiddleware


class TestAuthMiddleware:
    """Test cases for AuthMiddleware class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = Mock()
        self.middleware = AuthMiddleware(self.app)

    @pytest.mark.asyncio
    async def test_dispatch_public_path(self):
        """Test middleware bypass for public paths."""
        request = Mock(spec=Request)
        request.url.path = "/health"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await self.middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_missing_auth_header(self):
        """Test middleware with missing Authorization header."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = None

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["Error"]["Code"] == "UnauthorizedOperation"
        assert exc_info.value.detail["Error"]["Message"] == "Authorization header required"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_invalid_auth_header_format(self):
        """Test middleware with invalid Authorization header format."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = "Invalid token"

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["Error"]["Code"] == "UnauthorizedOperation"
        assert exc_info.value.detail["Error"]["Message"] == "Bearer token required"
        call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("middleware.auth.validate_jwt_token")
    @patch("middleware.auth.validate_jwt_claims")
    @patch("middleware.auth.set_user_context")
    @patch("middleware.auth.clear_user_context")
    @patch("middleware.auth.tracer")
    async def test_dispatch_successful_auth(
        self,
        mock_tracer,
        mock_clear_context,
        mock_set_context,
        mock_validate_claims,
        mock_validate_token,
    ):
        """Test successful authentication flow."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = "Bearer valid.jwt.token"
        request.headers = {"Authorization": "Bearer valid.jwt.token"}

        mock_claims = {"sub": "test", "aud": "test-audience", "client_id": "test-client-id"}
        mock_client_info = {
            "client_id": "test-client-id",
            "scope": "bedrockproxygateway:invoke",
        }

        mock_validate_token.return_value = mock_claims
        mock_validate_claims.return_value = mock_client_info

        # Setup mock tracer and span
        mock_validate_span = Mock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_validate_span)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = mock_context_manager

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await self.middleware.dispatch(request, call_next)

        assert result == expected_response

        mock_validate_token.assert_called_once_with("valid.jwt.token")
        mock_validate_claims.assert_called_once_with(mock_claims)
        mock_set_context.assert_called_once_with(
            "test-client-id", None, "bedrockproxygateway:invoke"
        )
        mock_clear_context.assert_called_once()
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("middleware.auth.validate_jwt_token")
    @patch("middleware.auth.tracer")
    @patch("middleware.auth.clear_user_context")
    async def test_dispatch_jwt_validation_error(
        self, mock_clear_context, mock_tracer, mock_validate_token
    ):
        """Test JWT validation error handling."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = "Bearer invalid.jwt.token"

        mock_validate_token.side_effect = ValueError("Token expired")

        # Setup mock tracer and span
        mock_validate_span = Mock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_validate_span)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = mock_context_manager

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail["Error"]["Code"] == "UnauthorizedOperation"
        assert exc_info.value.detail["Error"]["Message"] == "Invalid or expired token"
        mock_clear_context.assert_called_once()
        call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("middleware.auth.validate_jwt_token")
    @patch("middleware.auth.validate_jwt_claims")
    @patch("middleware.auth.tracer")
    @patch("middleware.auth.clear_user_context")
    async def test_dispatch_scope_validation_error(
        self, mock_clear_context, mock_tracer, mock_validate_claims, mock_validate_token
    ):
        """Test scope validation error handling."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = "Bearer valid.jwt.token"

        mock_claims = {"sub": "test", "aud": "test-audience"}
        mock_validate_token.return_value = mock_claims
        mock_validate_claims.side_effect = ValueError("Invalid scope: test:scope")

        # Setup mock tracer and span
        mock_validate_span = Mock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_validate_span)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = mock_context_manager

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware.dispatch(request, call_next)

        assert (
            exc_info.value.status_code == 403
        )  # Should be 403 since "scope" is in the error message
        assert exc_info.value.detail["Error"]["Code"] == "AccessDenied"
        assert exc_info.value.detail["Error"]["Message"] == "Insufficient permissions"
        mock_clear_context.assert_called_once()
        call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("middleware.auth.validate_jwt_token")
    @patch("middleware.auth.tracer")
    @patch("middleware.auth.clear_user_context")
    async def test_dispatch_unexpected_error(
        self, mock_clear_context, mock_tracer, mock_validate_token
    ):
        """Test unexpected error handling."""
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.headers.get.return_value = "Bearer valid.jwt.token"

        mock_validate_token.side_effect = Exception("Unexpected error")

        # Setup mock tracer and span
        mock_validate_span = Mock()
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__ = AsyncMock(return_value=mock_validate_span)
        mock_context_manager.__aexit__ = AsyncMock(return_value=None)
        mock_tracer.start_as_current_span.return_value = mock_context_manager

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await self.middleware.dispatch(request, call_next)

        assert (
            exc_info.value.status_code == 500
        )  # Should be 500 for unexpected Exception (not ValueError)
        assert exc_info.value.detail["Error"]["Code"] == "InternalServerError"
        assert exc_info.value.detail["Error"]["Message"] == "Authentication service error"
        mock_clear_context.assert_called_once()
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_public_paths_coverage(self):
        """Test all public paths are handled correctly."""
        public_paths = ["/", "/docs", "/openapi.json", "/redoc", "/health", "/debug"]

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        for path in public_paths:
            request = Mock(spec=Request)
            request.url.path = path

            result = await self.middleware.dispatch(request, call_next)

            assert result == expected_response
            call_next.assert_called_with(request)
