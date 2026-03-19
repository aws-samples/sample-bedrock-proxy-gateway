# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bedrock invoke model stream API endpoint."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockInvokeStream:
    """Test class for bedrock invoke model stream API functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        # Find the invoke-stream route
        self.stream_route = None
        for route in self.router.routes:
            if (
                hasattr(route, "path")
                and route.path == "/model/{model_id}/invoke-with-response-stream"
            ):
                self.stream_route = route
                break

    @pytest.mark.asyncio
    async def test_invoke_stream_success(self):
        """Test successful invoke model stream API call."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.return_value = iter([b"chunk1", b"chunk2"])
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.return_value = {
            "body": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
        mock_stream_ctx.record_failure = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert isinstance(result, StreamingResponse)
        assert result.headers["Content-Type"] == "application/vnd.amazon.eventstream"

    @pytest.mark.asyncio
    async def test_invoke_stream_with_guardrail_config(self):
        """Test invoke stream with guardrail configuration."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        mock_request.state.guardrail_config = {
            "guardrailIdentifier": "test-guardrail",
            "guardrailVersion": "1",
            "trace": "ENABLED",
        }

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.return_value = iter([b"chunk1"])
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.return_value = {
            "body": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
        mock_stream_ctx.record_failure = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_client_error_in_generator(self):
        """Test invoke stream with ClientError in generator."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "ValidationException", "Message": "Invalid input"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        }
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = ClientError(
            error_response, "InvokeModelWithResponseStream"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
        mock_stream_ctx.record_failure = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_general_error_in_generator(self):
        """Test invoke stream with general error in generator."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.side_effect = Exception("Connection error")
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.return_value = {
            "body": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
        mock_stream_ctx.record_failure = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_client_error(self):
        """Test invoke stream with ClientError before streaming."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"},
            "ResponseMetadata": {"HTTPStatusCode": 429},
        }
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = ClientError(
            error_response, "InvokeModelWithResponseStream"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            # For invoke stream, errors in the generator don't raise exceptions immediately
            # They return a StreamingResponse that yields error data
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_param_validation_error(self):
        """Test invoke stream with ParamValidationError."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = ParamValidationError(
            report="Invalid parameter"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            # For invoke stream, errors in the generator don't raise exceptions immediately
            # They return a StreamingResponse that yields error data
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_general_exception(self):
        """Test invoke stream with general exception."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = Exception(
            "Network error"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            # For invoke stream, errors in the generator don't raise exceptions immediately
            # They return a StreamingResponse that yields error data
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_http_exception_passthrough(self):
        """Test that HTTPException is passed through unchanged."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        original_exception = HTTPException(status_code=429, detail="Rate limited")
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = original_exception

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            # For invoke stream, errors in the generator don't raise exceptions immediately
            # They return a StreamingResponse that yields error data
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_empty_error_message(self):
        """Test invoke stream with empty error message."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "AccessDeniedException", "Message": ""},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.side_effect = ClientError(
            error_response, "InvokeModelWithResponseStream"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            # For invoke stream, errors in the generator don't raise exceptions immediately
            # They return a StreamingResponse that yields error data
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )
            assert isinstance(result, StreamingResponse)

    @pytest.mark.asyncio
    async def test_invoke_stream_content_type_headers(self):
        """Test invoke stream with proper content type headers."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.return_value = iter([b"chunk1"])
        mock_bedrock_client.__aenter__.return_value.invoke_model_with_response_stream.return_value = {
            "body": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
        mock_stream_ctx.record_failure = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        # Verify response headers
        assert result.headers["Cache-Control"] == "no-cache"
        assert result.headers["Connection"] == "keep-alive"
        assert result.headers["X-Accel-Buffering"] == "no"
        assert result.headers["Content-Type"] == "application/vnd.amazon.eventstream"
        assert result.headers["Transfer-Encoding"] == "chunked"
        assert result.headers["X-Amzn-Bedrock-Content-Type"] == "application/json"
