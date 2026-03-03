"""Unit tests for bedrock converse API endpoint."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockConverse:
    """Test class for bedrock converse API functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        # Find the converse route
        self.converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                self.converse_route = route
                break

    @pytest.mark.asyncio
    async def test_converse_success(self):
        """Test successful converse API call."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": "response"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": "end_turn",
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert "output" in result
        assert result["usage"]["inputTokens"] == 10
        mock_bedrock_client.__aenter__.return_value.converse.assert_called_once()

    @pytest.mark.asyncio
    async def test_converse_with_system_prompt(self):
        """Test converse with system prompt."""
        mock_request = Mock()
        request_body = {
            "messages": [{"role": "user", "content": "test"}],
            "system": "You are a helpful assistant",
        }
        mock_request.body = AsyncMock(return_value=json.dumps(request_body).encode())
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": "response"}]}},
            "usage": {"inputTokens": 15, "outputTokens": 25},
            "stopReason": "end_turn",
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result["usage"]["inputTokens"] == 15

    @pytest.mark.asyncio
    async def test_converse_with_tools(self):
        """Test converse with tool configuration."""
        mock_request = Mock()
        request_body = {
            "messages": [{"role": "user", "content": "test"}],
            "toolConfig": {"tools": [{"name": "test_tool"}]},
        }
        mock_request.body = AsyncMock(return_value=json.dumps(request_body).encode())
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": "response"}]}},
            "usage": {"inputTokens": 20, "outputTokens": 30},
            "stopReason": "tool_use",
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result["stopReason"] == "tool_use"

    @pytest.mark.asyncio
    async def test_converse_with_modified_body(self):
        """Test converse with modified body from middleware."""
        mock_request = Mock()
        mock_request.state.modified_body = {"messages": [{"role": "user", "content": "modified"}]}

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": "response"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": "end_turn",
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert "output" in result

    @pytest.mark.asyncio
    async def test_converse_client_error(self):
        """Test converse with ClientError."""
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
        mock_bedrock_client.__aenter__.return_value.converse.side_effect = ClientError(
            error_response, "Converse"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_converse_client_error_empty_message(self):
        """Test converse with ClientError having empty message."""
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
        mock_bedrock_client.__aenter__.return_value.converse.side_effect = ClientError(
            error_response, "Converse"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 403
        assert "Access denied for model" in exc_info.value.detail["Error"]["Message"]

    @pytest.mark.asyncio
    async def test_converse_param_validation_error(self):
        """Test converse with ParamValidationError."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.side_effect = ParamValidationError(
            report="Invalid parameter"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_converse_general_exception(self):
        """Test converse with general exception."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.side_effect = Exception(
            "Network error"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_converse_json_decode_error(self):
        """Test converse with invalid JSON."""
        mock_request = Mock()
        mock_request.body = AsyncMock(return_value=b"invalid json")

        mock_bedrock_client = AsyncMock()

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException),
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

    @pytest.mark.asyncio
    async def test_converse_with_metrics_response(self):
        """Test converse with metrics in response."""
        mock_request = Mock()
        mock_request.body = AsyncMock(
            return_value=json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        )
        # Ensure request.state doesn't have modified_body
        mock_request.state = Mock()
        del mock_request.state.modified_body  # This will make hasattr return False

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.converse.return_value = {
            "output": {"message": {"content": [{"text": "response"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": "end_turn",
            "metrics": {"latencyMs": 150},
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result["metrics"]["latencyMs"] == 150

    @pytest.mark.asyncio
    async def test_converse_http_exception_passthrough(self):
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
        mock_bedrock_client.__aenter__.return_value.converse.side_effect = original_exception

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.converse_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limited"
