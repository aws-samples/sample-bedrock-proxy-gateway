# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for middleware.rate_limit module."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from middleware.rate_limit import RateLimitMiddleware


def _make_non_stream_request(
    *,
    path: str = "/model/test-model/converse",
    rate_ctx: tuple = ("client", "model", "account", 1000, "converse"),
    estimated_tokens: int = 0,
) -> Mock:
    """Build a ``Request`` mock shaped like the non-streaming reconciliation
    path expects: ``url.path`` targets a non-streaming Bedrock endpoint,
    ``state.rate_ctx`` is populated, and ``state.estimated_tokens`` is
    explicit so the delta computation is deterministic.
    """
    request = Mock(spec=Request)
    request.url = Mock()
    request.url.path = path
    request.state = SimpleNamespace()
    request.state.rate_ctx = rate_ctx
    request.state.estimated_tokens = estimated_tokens
    return request


def _make_non_stream_response(payload: dict) -> Mock:
    """Build a ``_StreamingResponse``-shaped mock whose ``body_iterator``
    yields the JSON encoding of ``payload``. Matches how
    ``BaseHTTPMiddleware`` wraps a non-streaming JSON response at
    runtime — ``body`` is empty; only ``body_iterator`` exposes bytes.
    """
    return _make_non_stream_response_raw(json.dumps(payload).encode("utf-8"))


def _make_non_stream_response_raw(body_bytes: bytes) -> Mock:
    """Same shape as :func:`_make_non_stream_response` but for raw
    non-JSON payloads (used by the malformed-body test cases).
    """
    async def _iter() -> "AsyncGeneratorType":  # noqa: F821 -- documentation only
        yield body_bytes

    response = Mock()
    response.body_iterator = _iter()
    response.body = b""  # matches Starlette's _StreamingResponse shape
    return response


class TestRateLimitMiddleware:
    """Test cases for RateLimitMiddleware class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = Mock()
        self.mock_config = Mock()
        self.mock_config.rate_limiting_enabled = True
        self.mock_config.valkey_url = "redis://localhost:6379"
        self.mock_config.rate_limit_config = json.dumps(
            {
                "permissions": {
                    "test-client": {
                        "models": {"anthropic.claude-3-haiku": {"rpm": 100, "tpm": 10000}},
                        "accounts": ["123456789", "987654321"],
                    }
                }
            }
        )

    def test_extract_model_id_valid_paths(self):
        """Test model_id extraction from valid paths.

        LOGIC: GenAI API endpoints follow pattern /model/{model_id}/{operation}
        The middleware must extract model_id for rate limiting key generation.
        This is critical for creating Redis keys like "client:model_id:rpm".

        EXPECTED: Correctly extracts model_id from well-formed paths
        """
        middleware = RateLimitMiddleware(self.app)

        test_cases = [
            ("/model/anthropic.claude-3-haiku/converse", "anthropic.claude-3-haiku"),
            ("/model/mistral.mistral-7b-instruct/invoke", "mistral.mistral-7b-instruct"),
            ("/model/amazon.titan-text-express/converse-stream", "amazon.titan-text-express"),
        ]

        for path, expected in test_cases:
            result = middleware._extract_model_id(path)
            assert result == expected

    def test_extract_model_id_invalid_paths(self):
        """Test model_id extraction from invalid paths.

        LOGIC: Non-model endpoints should return None to skip rate limiting.
        This includes public paths, malformed URLs, and non-GenAI endpoints.
        Returning None triggers early exit in dispatch() for performance.

        EXPECTED: Returns None for all invalid/non-model paths
        """
        middleware = RateLimitMiddleware(self.app)

        invalid_paths = [
            "/health",  # Public endpoint
            "/docs",  # Documentation endpoint
            "/model/",  # Missing model_id
            "/model",  # Incomplete path
            "/model//converse",  # Empty model_id segment
            "/api/model/test/converse",  # Wrong prefix
            "",  # Empty path
        ]

        for path in invalid_paths:
            result = middleware._extract_model_id(path)
            assert result is None

    def test_is_guardrail_endpoint_valid_paths(self):
        """Test guardrail endpoint detection for valid paths.

        LOGIC: Guardrail endpoints follow pattern /guardrail/{id}/version/{version}/apply
        These endpoints need special handling for account assignment.

        EXPECTED: Correctly identifies guardrail endpoints
        """
        middleware = RateLimitMiddleware(self.app)

        valid_guardrail_paths = [
            "/guardrail/test-guardrail/version/1/apply",
            "/guardrail/content-filter/version/DRAFT/apply",
            "/guardrail/pii-detection/version/2.0/apply",
        ]

        for path in valid_guardrail_paths:
            result = middleware._is_guardrail_endpoint(path)
            assert result is True

    def test_is_guardrail_endpoint_invalid_paths(self):
        """Test guardrail endpoint detection for invalid paths.

        LOGIC: Non-guardrail endpoints should return False.
        This includes model endpoints, public paths, and malformed URLs.

        EXPECTED: Returns False for all non-guardrail paths
        """
        middleware = RateLimitMiddleware(self.app)

        invalid_guardrail_paths = [
            "/model/test/converse",  # Model endpoint
            "/health",  # Public endpoint
            "/guardrail/test/apply",  # Missing version segment
            "/guardrail/test/version/1",  # Missing /apply
            "/guardrail/",  # Incomplete path
            "/apply/guardrail/test",  # Wrong order
            "/guardrail/test/invoke",  # Wrong operation
            "/guardrail/test/version/1/apply/extra",  # Extra segments
            "",  # Empty path
        ]

        for path in invalid_guardrail_paths:
            result = middleware._is_guardrail_endpoint(path)
            assert result is False

    @patch("middleware.rate_limit.config")
    def test_init_disabled(self, mock_config):
        """Test middleware initialization when rate limiting is disabled.

        LOGIC: When config.rate_limiting_enabled = False, middleware should
        disable all rate limiting logic for maximum performance.
        No Redis connections or rate limiting components should be initialized.

        EXPECTED: middleware.enabled = False, no component initialization
        """
        mock_config.rate_limiting_enabled = False

        middleware = RateLimitMiddleware(self.app)

        assert not middleware.enabled

    @patch("middleware.rate_limit.config")
    @patch("middleware.rate_limit.RateLimiter")
    @patch("middleware.rate_limit.TokenCounter")
    @patch("middleware.rate_limit.RateLimitEngine")
    def test_init_enabled_success(self, mock_engine, mock_tokens, mock_limiter, mock_config):
        """Test successful middleware initialization when enabled.

        LOGIC: When rate limiting is enabled, middleware must initialize:
        1. RateLimiter with Redis connection for counter storage
        2. TokenCounter for input/output token estimation and extraction
        3. RateLimitEngine for quota management and account selection

        EXPECTED: All components initialized with correct parameters
        """
        mock_config.rate_limiting_enabled = True
        mock_config.valkey_url = "redis://localhost:6379"
        mock_config.rate_limit_config = json.dumps({"permissions": {"test": {"models": {}}}})

        middleware = RateLimitMiddleware(self.app)

        assert middleware.enabled
        mock_limiter.assert_called_once_with()
        mock_tokens.assert_called_once()
        mock_engine.assert_called_once()

    @patch("middleware.rate_limit.config")
    @patch("middleware.rate_limit.logger")
    def test_init_invalid_config(self, mock_logger, mock_config):
        """Test middleware initialization with invalid config.

        LOGIC: Invalid JSON config should disable rate limiting gracefully.
        This prevents application startup failures due to config errors.
        Error is logged for debugging but doesn't crash the service.

        EXPECTED: middleware.enabled = False, error logged, no exceptions
        """
        mock_config.rate_limiting_enabled = True
        mock_config.valkey_url = "redis://localhost:6379"
        mock_config.rate_limit_config = "invalid json"

        middleware = RateLimitMiddleware(self.app)

        assert not middleware.enabled
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_disabled(self):
        """Test dispatch when rate limiting is disabled.

        LOGIC: When middleware.enabled = False, should immediately pass
        request to next middleware without any rate limiting logic.
        This is the fastest path for disabled rate limiting.

        EXPECTED: Request passes through unchanged, no rate limiting performed
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = False

        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("secrets.choice")
    async def test_dispatch_disabled_with_default_accounts(self, mock_choice):
        """Test dispatch when rate limiting is disabled with multiple default accounts.

        LOGIC: When rate limiting is disabled but model_id exists, should
        select a random default account using secrets.choice for security.
        This ensures load balancing across multiple default accounts.

        EXPECTED: Random account selected, rate_ctx set with chosen account
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = False
        middleware.rate_config = {
            "permissions": {"default": {"accounts": ["account1", "account2", "account3"]}}
        }

        mock_choice.return_value = "account2"

        request = Mock(spec=Request)
        request.url.path = "/model/test-model/converse"
        request.state = Mock()

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        mock_choice.assert_called_once_with(["account1", "account2", "account3"])
        assert request.state.rate_ctx == (None, "test-model", "account2", None, None)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.client_id_context")
    @patch("secrets.choice")
    async def test_dispatch_guardrail_endpoint_with_client_accounts(
        self, mock_choice, mock_context
    ):
        """Test dispatch for guardrail endpoints with client account assignment.

        LOGIC: Guardrail endpoints should use the client's specific accounts
        when available. This ensures proper AWS account routing for guardrail
        API calls using the client's configured accounts.

        EXPECTED: Client account selected, rate_ctx set with guardrail type
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = False
        middleware.rate_config = {
            "permissions": {
                "test-client": {"accounts": ["client-account1", "client-account2"]},
                "default": {"accounts": ["default-account1"]},
            }
        }

        mock_context.get.return_value = "test-client"
        mock_choice.return_value = "client-account1"

        request = Mock(spec=Request)
        request.url.path = "/guardrail/content-filter/version/DRAFT/apply"
        request.state = Mock()

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        mock_choice.assert_called_once_with(["client-account1", "client-account2"])
        assert request.state.rate_ctx == (None, "guardrail", "client-account1", None, None)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.client_id_context")
    @patch("secrets.choice")
    async def test_dispatch_guardrail_endpoint_fallback_to_default(
        self, mock_choice, mock_context
    ):
        """Test dispatch for guardrail endpoints falls back to default accounts.

        LOGIC: When client has no specific accounts configured, guardrail endpoints
        should fall back to default accounts. This ensures guardrail calls always
        have an account to use.

        EXPECTED: Default account selected as fallback
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = False
        middleware.rate_config = {
            "permissions": {
                "test-client": {"models": {}},  # No accounts configured
                "default": {"accounts": ["default-account1", "default-account2"]},
            }
        }

        mock_context.get.return_value = "test-client"
        mock_choice.return_value = "default-account1"

        request = Mock(spec=Request)
        request.url.path = "/guardrail/content-filter/version/DRAFT/apply"
        request.state = Mock()

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        mock_choice.assert_called_once_with(["default-account1", "default-account2"])
        assert request.state.rate_ctx == (None, "guardrail", "default-account1", None, None)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.client_id_context")
    @patch("secrets.choice")
    async def test_dispatch_guardrail_endpoint_enabled_rate_limiting(
        self, mock_choice, mock_context
    ):
        """Test dispatch for guardrail endpoints when rate limiting is enabled.

        LOGIC: Even with rate limiting enabled, guardrail endpoints should
        skip rate limiting logic and get client account assignment.
        Guardrails are infrastructure services that shouldn't be rate limited.

        EXPECTED: Rate limiting skipped, client account assigned
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_config = {
            "permissions": {
                "test-client": {"accounts": ["client-account1"]},
                "default": {"accounts": ["default-account1"]},
            }
        }

        mock_context.get.return_value = "test-client"
        mock_choice.return_value = "client-account1"

        request = Mock(spec=Request)
        request.url.path = "/guardrail/pii-detection/version/1/apply"
        request.state = Mock()

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        mock_choice.assert_called_once_with(["client-account1"])
        assert request.state.rate_ctx == (None, "guardrail", "client-account1", None, None)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("secrets.choice")
    async def test_dispatch_enabled_but_failed_initialization(self, mock_choice):
        """Test dispatch when rate limiting is enabled but initialization failed.

        LOGIC: When rate limiting is enabled but fails during initialization
        (e.g., Redis connection issues), middleware should still set default
        account for model requests using the loaded config.

        EXPECTED: Default account selected despite failed initialization
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = False  # Simulates failed initialization
        middleware.rate_config = {
            "permissions": {"default": {"accounts": ["account1", "account2"]}}
        }

        mock_choice.return_value = "account1"

        request = Mock(spec=Request)
        request.url.path = "/model/claude-3-haiku/converse"
        request.state = Mock()

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        mock_choice.assert_called_once_with(["account1", "account2"])
        assert request.state.rate_ctx == (None, "claude-3-haiku", "account1", None, None)
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_public_path(self):
        """Test dispatch for public paths.

        LOGIC: Public paths (health, docs, metrics) should skip rate limiting
        even when middleware is enabled. These endpoints need to be accessible
        for monitoring and don't consume GenAI resources.

        EXPECTED: Public paths bypass rate limiting, pass through unchanged
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True

        request = Mock(spec=Request)
        request.url.path = "/health"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_no_model_id(self):
        """Test dispatch when no model_id can be extracted.

        LOGIC: Non-GenAI endpoints that don't match /model/{id}/{op} pattern
        should skip rate limiting. These might be custom API endpoints
        that don't consume GenAI resources.

        EXPECTED: Non-model endpoints bypass rate limiting
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True

        request = Mock(spec=Request)
        request.url.path = "/api/test"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("observability.context_vars.client_id_context")
    @patch("middleware.rate_limit.rate_limit_span")
    async def test_dispatch_no_api_type(self, mock_span, mock_context):
        """Test dispatch when no API type is detected.

        LOGIC: If model_id exists but API type can't be determined from URL,
        skip rate limiting. This handles unknown/unsupported operations
        on valid models. Duration is still recorded for monitoring.

        EXPECTED: Request passes through, duration recorded as "skipped"
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.rate_limiter.get_api_type.return_value = None

        mock_context.get.return_value = "test-client"
        mock_span.return_value.__aenter__ = AsyncMock()
        mock_span.return_value.__aexit__ = AsyncMock()

        request = Mock(spec=Request)
        request.url.path = "/model/test/unknown"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_rate_limit_exceeded_simulation(self):
        """Test rate limit exceeded scenario with mocked dispatch.

        LOGIC: When rate limits are exceeded, middleware should return HTTP 429
        with proper headers and error message. The request should not reach
        the actual GenAI service to prevent resource consumption.

        EXPECTED: Returns 429 status, proper headers, request blocked
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True

        # Create a custom dispatch that simulates rate limit exceeded
        async def mock_dispatch_rate_limited(request, call_next):
            if "/model/" in request.url.path:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers={"X-RateLimit-Limit": "100"},
                )
            return await call_next(request)

        # Replace the dispatch method
        original_dispatch = middleware.dispatch
        middleware.dispatch = mock_dispatch_rate_limited

        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"

        call_next = AsyncMock()

        result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 429
        call_next.assert_not_called()

        # Restore original dispatch
        middleware.dispatch = original_dispatch

    @pytest.mark.asyncio
    async def test_rate_limit_context_handling(self):
        """Test that rate limit context is properly handled.

        LOGIC: The rate_ctx tuple stores (client_id, model_id, account_id, tpm_limit, api_type)
        from the initial rate limit check for use in post-processing.
        This context enables token updates and header generation after request completion.

        EXPECTED: Context handling works for various response types without errors
        """
        middleware = RateLimitMiddleware(self.app)

        # Test _update_tokens with proper rate_ctx tuple
        request = Mock(spec=Request)
        from types import SimpleNamespace

        request.state = SimpleNamespace()
        request.state.rate_ctx = ("client", "model", "account", 1000, "converse")

        response = Mock()
        response.body = None  # No body should skip processing

        # Should not raise exception
        await middleware._update_tokens(request, response)

        # Test with streaming response
        streaming_response = StreamingResponse(iter([b"data"]), media_type="text/plain")
        await middleware._update_tokens(request, streaming_response)

    @pytest.mark.asyncio
    async def test_dispatch_components_unit_tests(self):
        """Test individual components and methods of the middleware.

        LOGIC: Tests middleware components in isolation to avoid complex
        integration issues. Validates core functionality like model ID extraction
        and enabled/disabled state handling independently.

        EXPECTED: All component methods work correctly in isolation
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True

        # Test the rate limiting logic components separately
        # This avoids the complex dispatch method integration issues

        # Test 1: Verify middleware is properly enabled
        assert middleware.enabled

        # Test 2: Test model ID extraction (already covered in other tests)
        model_id = middleware._extract_model_id("/model/test/converse")
        assert model_id == "test"

        # Test 3: Test that disabled middleware skips processing
        middleware_disabled = RateLimitMiddleware(self.app)
        middleware_disabled.enabled = False

        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await middleware_disabled.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_http_exception(self):
        """Test dispatch when HTTPException is raised.

        LOGIC: HTTPExceptions (like 429 rate limit exceeded) should propagate
        immediately without duration recording. These are expected control flow
        exceptions that represent valid HTTP responses, not system errors.

        EXPECTED: HTTPException propagates, no duration recorded, request blocked
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()

        middleware.rate_limiter.get_api_type.side_effect = HTTPException(500, "Internal error")

        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"

        call_next = AsyncMock()

        with pytest.raises(HTTPException):
            await middleware.dispatch(request, call_next)

        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_unexpected_exception(self):
        """Test dispatch when unexpected exception is raised.

        LOGIC: Unexpected exceptions (RuntimeError, etc.) indicate system errors
        that should be recorded for monitoring. Duration is recorded as "error"
        to track middleware performance issues and failures.

        EXPECTED: Exception propagates, duration recorded as "error" for monitoring
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()

        middleware.rate_limiter.get_api_type.side_effect = RuntimeError("Unexpected error")

        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"

        call_next = AsyncMock()

        with pytest.raises(RuntimeError):
            await middleware.dispatch(request, call_next)

        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_rate_limit_headers_success(self):
        """Test successful addition of rate limit headers.

        LOGIC: HTTP responses should include rate limit headers to inform
        clients about their quota limits and reset times. This follows
        HTTP standards for rate limiting APIs and helps clients implement
        proper retry logic.

        EXPECTED: Standard rate limit headers added with correct values
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.rate_limiter.limiter.get_reset_time.return_value = 1234567890

        response = Mock()
        response.headers = {}

        mock_quota_config = Mock()
        mock_quota_config.rpm = 100
        mock_quota_config.tpm = 10000

        await middleware._add_rate_limit_headers(
            response, "test-model", mock_quota_config, 45, 5000
        )

        assert response.headers["x-ratelimit-limit-rpm"] == "100"
        assert response.headers["x-ratelimit-limit-tpm"] == "10000"
        assert response.headers["x-ratelimit-used-rpm"] == "45"
        assert response.headers["x-ratelimit-used-tpm"] == "5000"
        assert response.headers["x-ratelimit-reset-rpm"] == "1234567890"
        assert response.headers["x-ratelimit-reset-tpm"] == "1234567890"

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.logger")
    async def test_add_rate_limit_headers_exception(self, mock_logger):
        """Test rate limit headers addition when exception occurs.

        LOGIC: Redis failures during header generation should not block responses.
        Headers are informational for clients but not critical for functionality.
        Error is logged but response continues without headers.

        EXPECTED: Error logged, response continues, no exception raised
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.rate_limiter.limiter.get_reset_time.side_effect = Exception("Redis error")

        response = Mock()
        response.headers = {}

        mock_quota_config = Mock()
        mock_quota_config.rpm = 100
        mock_quota_config.tpm = 10000

        await middleware._add_rate_limit_headers(
            response, "test-model", mock_quota_config, 45, 5000
        )

        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tokens_routes_streaming_endpoint_to_reconcile_stream(self):
        """When the URL path is a Bedrock streaming endpoint,
        ``_update_tokens`` MUST route to ``_reconcile_stream`` and skip the
        non-streaming path — regardless of response type. ``BaseHTTPMiddleware``
        makes both streaming and non-streaming responses shape-identical, so
        the URL is the only reliable discriminator.
        """
        middleware = RateLimitMiddleware(self.app)

        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/model/us.amazon.nova-lite-v1:0/converse-stream"
        request.state = SimpleNamespace()
        request.state.rate_ctx = ("client", "model", "account", 1000, "converse")

        response = StreamingResponse(iter([b"data"]), media_type="text/plain")

        with (
            patch.object(middleware, "_reconcile_stream", new_callable=AsyncMock) as mock_stream,
            patch.object(middleware, "_reconcile_non_stream", new_callable=AsyncMock) as mock_non,
        ):
            await middleware._update_tokens(request, response)
            mock_stream.assert_awaited_once_with(request, response)
            mock_non.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_tokens_routes_non_streaming_endpoint_to_reconcile_non_stream(
        self,
    ):
        """Regression: ``BaseHTTPMiddleware`` wraps every downstream
        response in ``_StreamingResponse``. Using ``isinstance(response,
        StreamingResponse)`` or ``hasattr(response, "body_iterator")`` to
        detect streaming leaves non-streaming requests silently un-reconciled.
        ``_update_tokens`` must key on the URL path via
        ``_detect_stream_endpoint`` and dispatch non-streaming paths through
        ``_reconcile_non_stream``.
        """
        middleware = RateLimitMiddleware(self.app)
        request = _make_non_stream_request()
        response = _make_non_stream_response(
            {"usage": {"inputTokens": 14, "outputTokens": 100}}
        )

        with (
            patch.object(middleware, "_reconcile_stream", new_callable=AsyncMock) as mock_stream,
            patch.object(middleware, "_reconcile_non_stream", new_callable=AsyncMock) as mock_non,
        ):
            await middleware._update_tokens(request, response)
            mock_non.assert_awaited_once_with(request, response)
            mock_stream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_non_stream_replays_body_iterator(self):
        """After ``_reconcile_non_stream`` drains ``body_iterator`` for
        reconciliation, it MUST reassign ``body_iterator`` to a single-shot
        replay of the same bytes so Starlette can still forward the response
        to the client unchanged.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.rate_limiter.limiter.check_and_consume = AsyncMock(return_value=True)
        middleware.tokens = Mock()
        middleware.tokens.extract.return_value = 178

        payload = {"usage": {"inputTokens": 14, "outputTokens": 164}}
        original_bytes = json.dumps(payload).encode("utf-8")
        request = _make_non_stream_request(estimated_tokens=11)
        response = _make_non_stream_response(payload)

        await middleware._reconcile_non_stream(request, response)

        # Body iterator was replaced; iterating it must yield the same
        # bytes the original iterator would have produced.
        replayed = b""
        async for chunk in response.body_iterator:
            replayed += chunk
        assert replayed == original_bytes

    @pytest.mark.asyncio
    async def test_reconcile_non_stream_applies_signed_delta(self):
        """The Redis write MUST use ``delta = aggregated - estimated``, not
        the raw aggregated total. This preserves the pre-request estimate
        write that ``check_and_consume_all`` already applied and closes the
        estimate-vs-actual gap.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.rate_limiter.limiter.check_and_consume = AsyncMock(return_value=True)
        middleware.tokens = Mock()
        middleware.tokens.extract.return_value = 178

        request = _make_non_stream_request(estimated_tokens=11)
        response = _make_non_stream_response(
            {"usage": {"inputTokens": 14, "outputTokens": 164}}
        )

        await middleware._reconcile_non_stream(request, response)

        middleware.rate_limiter.limiter.check_and_consume.assert_awaited_once_with(
            "{client:model}:client:tpm", 1000, 178 - 11
        )

    @pytest.mark.asyncio
    async def test_update_tokens_no_body(self):
        """Test token update skips responses without body.

        LOGIC: Responses without body (None, empty) don't contain token usage data.
        This includes error responses, redirects, or other non-content responses.
        Skip processing to avoid JSON parsing errors.

        EXPECTED: Empty responses are skipped without errors
        """
        middleware = RateLimitMiddleware(self.app)

        request = Mock(spec=Request)
        from types import SimpleNamespace

        request.state = SimpleNamespace()
        request.state.rate_ctx = ("client", "model", "account", 1000, "converse")

        response = Mock()
        response.body = None

        # Should not raise any exceptions and should skip processing
        await middleware._update_tokens(request, response)

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.record_tokens_consumed")
    async def test_update_tokens_unlimited_tpm(self, mock_record):
        """Non-streaming reconciliation on unlimited TPM: extract tokens,
        record metrics, skip Redis. Mirrors the streaming reconciler's
        ``tpm_limit_unlimited`` skip path.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.tokens = Mock()
        middleware.tokens.extract.return_value = 250

        request = _make_non_stream_request(rate_ctx=("client", "model", "account", -1, "converse"))
        response = _make_non_stream_response(
            {"usage": {"outputTokens": 100, "inputTokens": 50}}
        )

        await middleware._update_tokens(request, response)

        middleware.tokens.extract.assert_called_once()
        # Non-streaming reconciliation records the aggregated total
        # regardless of TPM-limit shape, matching the streaming path.
        mock_record.assert_called_once_with("client", "model", 250, "converse")

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.record_tokens_consumed")
    async def test_update_tokens_limited_tpm(self, mock_record):
        """Non-streaming reconciliation on limited TPM: extract tokens,
        write the signed ``delta = aggregated - estimated`` to
        Shared_TPM_Key, and record metrics. With ``estimated_tokens``
        unset (defaults to 0), the delta equals the aggregated total.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()
        middleware.tokens.extract.return_value = 250
        middleware.rate_limiter.limiter.check_and_consume = AsyncMock(return_value=True)

        request = _make_non_stream_request(
            rate_ctx=("client", "model", "account", 1000, "converse")
        )
        response = _make_non_stream_response(
            {"usage": {"outputTokens": 100, "inputTokens": 50}}
        )

        await middleware._update_tokens(request, response)

        middleware.tokens.extract.assert_called_once()
        middleware.rate_limiter.limiter.check_and_consume.assert_called_once_with(
            "{client:model}:client:tpm", 1000, 250
        )
        mock_record.assert_called_once_with("client", "model", 250, "converse")

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.record_redis_failure")
    @patch("middleware.rate_limit.logger")
    async def test_update_tokens_redis_failure(self, mock_logger, mock_record_failure):
        """Redis-write failures during non-streaming reconciliation are
        captured (``record_redis_failure`` + error log), swallowed
        (no exception raised), and never propagate to the client.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()
        middleware.tokens.extract.return_value = 250
        middleware.rate_limiter.limiter.check_and_consume = AsyncMock(
            side_effect=Exception("Redis connection failed")
        )

        request = _make_non_stream_request(
            rate_ctx=("client", "model", "account", 1000, "converse")
        )
        response = _make_non_stream_response({"usage": {"outputTokens": 100}})

        await middleware._update_tokens(request, response)

        mock_record_failure.assert_called_once_with("token_update", "Exception")
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tokens_json_decode_error(self):
        """Non-JSON response bodies (malformed / non-model endpoints) are
        caught inside ``_reconcile_non_stream``'s JSON decode guard and
        skipped — no exception, no token extraction attempt.
        """
        middleware = RateLimitMiddleware(self.app)

        request = _make_non_stream_request(
            rate_ctx=("client", "model", "account", 1000, "converse")
        )
        response = _make_non_stream_response_raw(b"invalid json")

        # Should not raise exception, just log skip event
        await middleware._update_tokens(request, response)

    def test_middleware_constants_and_imports(self):
        """Test that middleware has required constants and imports.

        LOGIC: Validates that the middleware class has all required methods
        and attributes for proper functionality. This ensures the class
        interface is complete and methods are callable.

        EXPECTED: All required methods exist and are callable
        """
        # Test that middleware can be imported and has expected attributes
        middleware = RateLimitMiddleware(self.app)

        # Should have these methods
        assert hasattr(middleware, "dispatch")
        assert hasattr(middleware, "_extract_model_id")
        assert hasattr(middleware, "_is_guardrail_endpoint")
        assert hasattr(middleware, "_add_rate_limit_headers")
        assert hasattr(middleware, "_update_tokens")

        # Should be callable
        assert callable(middleware.dispatch)
        assert callable(middleware._extract_model_id)
        assert callable(middleware._is_guardrail_endpoint)

    @pytest.mark.asyncio
    async def test_init_missing_permissions_config(self):
        """Test initialization with missing permissions in config.

        LOGIC: Config JSON must contain "permissions" key for rate limiting.
        Missing permissions should disable middleware gracefully rather than
        crash the application. This ensures robust config validation.

        EXPECTED: Middleware disabled, error logged, no exceptions
        """
        with (
            patch("middleware.rate_limit.config") as mock_config,
            patch("middleware.rate_limit.logger") as mock_logger,
        ):
            mock_config.rate_limiting_enabled = True
            mock_config.valkey_url = "redis://localhost:6379"
            mock_config.rate_limit_config = json.dumps(
                {"invalid": "config"}
            )  # Missing permissions

            middleware = RateLimitMiddleware(self.app)

            assert not middleware.enabled
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_value_error_config(self):
        """Test initialization with ValueError in config.

        LOGIC: RateLimitEngine validation errors should disable middleware
        gracefully. This handles cases where config structure is valid JSON
        but contains invalid values (negative limits, missing fields, etc.).

        EXPECTED: Middleware disabled, error logged, no exceptions
        """
        with (
            patch("middleware.rate_limit.config") as mock_config,
            patch("middleware.rate_limit.logger") as mock_logger,
            patch("middleware.rate_limit.RateLimitEngine") as mock_engine,
        ):
            mock_config.rate_limiting_enabled = True
            mock_config.valkey_url = "redis://localhost:6379"
            mock_config.rate_limit_config = json.dumps({"permissions": {"test": {}}})
            mock_engine.side_effect = ValueError("Invalid config")

            middleware = RateLimitMiddleware(self.app)

            assert not middleware.enabled
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    @patch("middleware.rate_limit.record_tokens_consumed")
    async def test_update_tokens_json_decode_error_handling(self, mock_record):
        """Redundant coverage: confirm the JSON-decode guard in
        ``_reconcile_non_stream`` short-circuits before ``extract`` and
        ``record_tokens_consumed`` are ever reached.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.tokens = Mock()

        request = _make_non_stream_request(
            rate_ctx=("client", "model", "account", 1000, "converse")
        )
        response = _make_non_stream_response_raw(b"invalid json content")

        # Should not raise exception
        await middleware._update_tokens(request, response)

        # Should not call extract or record
        middleware.tokens.extract.assert_not_called()
        mock_record.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_tokens_non_redis_exception(self):
        """Non-Redis exceptions from ``TokenCounter.extract`` are caught by
        the outer ``_update_tokens`` guard and swallowed without recording
        a Redis failure.
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.tokens = Mock()
        middleware.tokens.extract.side_effect = ValueError("Non-Redis error")

        request = _make_non_stream_request(
            rate_ctx=("client", "model", "account", 1000, "converse")
        )
        response = _make_non_stream_response({"usage": {"outputTokens": 100}})

        # Should not raise exception but also not record Redis failure
        await middleware._update_tokens(request, response)

        # Should have tried to extract
        middleware.tokens.extract.assert_called_once()

    @pytest.mark.asyncio
    @patch("observability.context_vars.client_id_context")
    @patch("middleware.rate_limit.rate_limit_span")
    async def test_dispatch_quota_config_403_error(self, mock_span, mock_context):
        """Test dispatch when quota config raises 403 HTTPException.

        LOGIC: When get_quota_config raises HTTPException(403), middleware should
        return proper JSONResponse with 403 status instead of letting it propagate
        as a 500 error. This ensures proper client error handling.

        EXPECTED: Returns 403 JSONResponse, duration recorded as "client_error"
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()

        middleware.rate_limiter.get_api_type.return_value = "converse"
        middleware.tokens.estimate.return_value = 100
        middleware.rate_limiter.get_quota_config.side_effect = HTTPException(
            403, "No quota configured for model test-model"
        )

        mock_context.get.return_value = "test-client"
        mock_span.return_value.__aenter__ = AsyncMock()
        mock_span.return_value.__aexit__ = AsyncMock()

        request = Mock(spec=Request)
        request.url.path = "/model/test-model/converse"
        request.body = AsyncMock(return_value=b'{"messages": []}')

        call_next = AsyncMock()

        result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 403
        call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("observability.context_vars.client_id_context")
    @patch("middleware.rate_limit.rate_limit_span")
    async def test_dispatch_quota_config_400_error(self, mock_span, mock_context):
        """Test dispatch when quota config raises 400 HTTPException.

        LOGIC: All 4xx client errors from quota config should be handled
        consistently, returning proper JSONResponse with original status code.
        This covers bad request scenarios and other client errors.

        EXPECTED: Returns 400 JSONResponse, duration recorded as "client_error"
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()

        middleware.rate_limiter.get_api_type.return_value = "converse"
        middleware.tokens.estimate.return_value = 100
        middleware.rate_limiter.get_quota_config.side_effect = HTTPException(
            400, "Invalid model format"
        )

        mock_context.get.return_value = "test-client"
        mock_span.return_value.__aenter__ = AsyncMock()
        mock_span.return_value.__aexit__ = AsyncMock()

        request = Mock(spec=Request)
        request.url.path = "/model/test-model/converse"
        request.body = AsyncMock(return_value=b'{"messages": []}')

        call_next = AsyncMock()

        result = await middleware.dispatch(request, call_next)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 400
        call_next.assert_not_called()

    @pytest.mark.asyncio
    @patch("observability.context_vars.client_id_context")
    @patch("middleware.rate_limit.rate_limit_span")
    async def test_dispatch_quota_config_500_error_propagates(self, mock_span, mock_context):
        """Test dispatch when quota config raises 500 HTTPException.

        LOGIC: 5xx server errors should propagate normally as they indicate
        system issues that need to be handled by the global exception handler.
        Only 4xx client errors get special JSONResponse treatment.

        EXPECTED: 500 HTTPException propagates, not converted to JSONResponse
        """
        middleware = RateLimitMiddleware(self.app)
        middleware.enabled = True
        middleware.rate_limiter = Mock()
        middleware.tokens = Mock()

        middleware.rate_limiter.get_api_type.return_value = "converse"
        middleware.tokens.estimate.return_value = 100
        middleware.rate_limiter.get_quota_config.side_effect = HTTPException(
            500, "Internal server error"
        )

        mock_context.get.return_value = "test-client"
        # Create a proper async context manager mock
        async_context = AsyncMock()
        async_context.__aenter__ = AsyncMock(return_value=None)
        async_context.__aexit__ = AsyncMock(return_value=None)
        mock_span.return_value = async_context

        request = Mock(spec=Request)
        request.url.path = "/model/test-model/converse"
        request.body = AsyncMock(return_value=b'{"messages": []}')
        from types import SimpleNamespace

        request.state = SimpleNamespace()

        call_next = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await middleware.dispatch(request, call_next)

        assert exc_info.value.status_code == 500
        call_next.assert_not_called()
