"""Unit tests for bedrock converse stream API endpoint."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockConverseStream:
    """Test class for bedrock converse stream API functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        # Find the converse-stream route
        self.stream_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse-stream":
                self.stream_route = route
                break

    @pytest.mark.asyncio
    async def test_converse_stream_success(self):
        """Test successful converse stream API call."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.return_value = iter([b"chunk1", b"chunk2", b"chunk3"])
        mock_bedrock_client.__aenter__.return_value.converse_stream.return_value = {
            "stream": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
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
    async def test_converse_stream_with_modified_body(self):
        """Test converse stream with modified body from middleware."""
        mock_request = Mock()
        mock_request.state.modified_body = {"messages": [{"role": "user", "content": "modified"}]}

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.return_value = iter([b"chunk1"])
        mock_bedrock_client.__aenter__.return_value.converse_stream.return_value = {
            "stream": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
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
    async def test_converse_stream_no_stream_body(self):
        """Test converse stream with no stream body in response."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse_stream.return_value = {}

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
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
    async def test_converse_stream_client_error_in_generator(self):
        """Test converse stream with ClientError in generator."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        error_response = {
            "Error": {"Code": "ThrottlingException", "Message": "Rate limit exceeded"},
            "ResponseMetadata": {"HTTPStatusCode": 429},
        }
        mock_stream._raw_stream.stream.side_effect = ClientError(error_response, "ConverseStream")
        mock_bedrock_client.__aenter__.return_value.converse_stream.return_value = {
            "stream": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
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
    async def test_converse_stream_general_error_in_generator(self):
        """Test converse stream with general error in generator."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_stream = Mock()
        mock_stream._raw_stream.stream.side_effect = Exception("Network error")
        mock_bedrock_client.__aenter__.return_value.converse_stream.return_value = {
            "stream": mock_stream
        }

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_stream_ctx.record_first_token = Mock()
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
    async def test_converse_stream_client_error(self):
        """Test converse stream with ClientError before streaming."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "ValidationException", "Message": "Invalid input"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        }
        mock_bedrock_client.__aenter__.return_value.converse_stream.side_effect = ClientError(
            error_response, "ConverseStream"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_converse_stream_param_validation_error(self):
        """Test converse stream with ParamValidationError."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse_stream.side_effect = (
            ParamValidationError(report="Invalid parameter")
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_converse_stream_general_exception(self):
        """Test converse stream with general exception."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse_stream.side_effect = Exception(
            "Network error"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_converse_stream_json_decode_error(self):
        """Test converse stream with invalid JSON."""
        mock_request = Mock()
        mock_request.body = AsyncMock(return_value=b"invalid json")

        mock_bedrock_client = AsyncMock()

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException),
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

    @pytest.mark.asyncio
    async def test_converse_stream_http_exception_passthrough(self):
        """Test that HTTPException is passed through unchanged."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        original_exception = HTTPException(status_code=429, detail="Rate limited")
        mock_bedrock_client.__aenter__.return_value.converse_stream.side_effect = (
            original_exception
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limited"

    @pytest.mark.asyncio
    async def test_converse_stream_empty_error_message(self):
        """Test converse stream with empty error message."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "AccessDeniedException", "Message": ""},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }
        mock_bedrock_client.__aenter__.return_value.converse_stream.side_effect = ClientError(
            error_response, "ConverseStream"
        )

        mock_metrics = Mock()
        mock_stream_ctx = Mock()
        mock_metrics.track_stream_request = AsyncMock()
        mock_metrics.track_stream_request.return_value.__aenter__ = AsyncMock(
            return_value=mock_stream_ctx
        )
        mock_metrics.track_stream_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.stream_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 403
        assert "Access denied for model" in exc_info.value.detail["Error"]["Message"]
