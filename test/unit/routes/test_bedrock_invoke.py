# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bedrock invoke model API endpoint."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockInvoke:
    """Test class for bedrock invoke model API functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        # Find the invoke route
        self.invoke_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/invoke":
                self.invoke_route = route
                break

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        """Test successful invoke model API call."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_response_body = Mock()
        mock_response_body.read.return_value = json.dumps({"completion": "test response"}).encode()
        mock_bedrock_client.__aenter__.return_value.invoke_model.return_value = {
            "body": mock_response_body
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result == {"completion": "test response"}
        mock_bedrock_client.__aenter__.return_value.invoke_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_with_guardrail_config(self):
        """Test invoke with guardrail configuration."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        mock_request.state.guardrail_config = {
            "guardrailIdentifier": "test-guardrail",
            "guardrailVersion": "1",
            "trace": "ENABLED",
        }

        mock_bedrock_client = AsyncMock()
        mock_response_body = Mock()
        mock_response_body.read.return_value = json.dumps({"completion": "test response"}).encode()
        mock_bedrock_client.__aenter__.return_value.invoke_model.return_value = {
            "body": mock_response_body
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result == {"completion": "test response"}
        # Verify guardrail parameters were passed
        call_args = mock_bedrock_client.__aenter__.return_value.invoke_model.call_args[1]
        assert call_args["guardrailIdentifier"] == "test-guardrail"
        assert call_args["guardrailVersion"] == "1"
        assert call_args["trace"] == "ENABLED"

    @pytest.mark.asyncio
    async def test_invoke_with_partial_guardrail_config(self):
        """Test invoke with partial guardrail configuration."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        mock_request.state.guardrail_config = {
            "guardrailIdentifier": "test-guardrail",
            # Missing guardrailVersion
        }

        mock_bedrock_client = AsyncMock()
        mock_response_body = Mock()
        mock_response_body.read.return_value = json.dumps({"completion": "test response"}).encode()
        mock_bedrock_client.__aenter__.return_value.invoke_model.return_value = {
            "body": mock_response_body
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result == {"completion": "test response"}
        # Verify guardrail parameters were not passed due to missing version
        call_args = mock_bedrock_client.__aenter__.return_value.invoke_model.call_args[1]
        assert "guardrailIdentifier" not in call_args

    @pytest.mark.asyncio
    async def test_invoke_client_error(self):
        """Test invoke with ClientError."""
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
        mock_bedrock_client.__aenter__.return_value.invoke_model.side_effect = ClientError(
            error_response, "InvokeModel"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_invoke_client_error_empty_message(self):
        """Test invoke with ClientError having empty message."""
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
        mock_bedrock_client.__aenter__.return_value.invoke_model.side_effect = ClientError(
            error_response, "InvokeModel"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 403
        assert "Access denied for model" in exc_info.value.detail["Error"]["Message"]

    @pytest.mark.asyncio
    async def test_invoke_param_validation_error(self):
        """Test invoke with ParamValidationError."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.invoke_model.side_effect = (
            ParamValidationError(report="Invalid model ID")
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.invoke_route.endpoint(
                model_id="invalid-model", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invoke_general_exception(self):
        """Test invoke with general exception."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.invoke_model.side_effect = Exception(
            "Unexpected error"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_invoke_http_exception_passthrough(self):
        """Test that HTTPException is passed through unchanged."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        original_exception = HTTPException(status_code=429, detail="Rate limited")
        mock_bedrock_client.__aenter__.return_value.invoke_model.side_effect = original_exception

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limited"

    @pytest.mark.asyncio
    async def test_invoke_complex_request_body(self):
        """Test invoke with complex request body."""
        mock_request = Mock()
        complex_body = {
            "prompt": "test prompt",
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "stop_sequences": ["Human:", "Assistant:"],
        }
        mock_request.json = AsyncMock(return_value=complex_body)
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_response_body = Mock()
        mock_response_body.read.return_value = json.dumps(
            {"completion": "complex response"}
        ).encode()
        mock_bedrock_client.__aenter__.return_value.invoke_model.return_value = {
            "body": mock_response_body
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        assert result == {"completion": "complex response"}
        # Verify the body was properly serialized
        call_args = mock_bedrock_client.__aenter__.return_value.invoke_model.call_args[1]
        assert json.loads(call_args["body"]) == complex_body

    @pytest.mark.asyncio
    async def test_invoke_content_type_headers(self):
        """Test invoke with proper content type headers."""
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value={"prompt": "test prompt"})
        # Ensure request.state doesn't have guardrail_config
        mock_request.state = Mock()
        del mock_request.state.guardrail_config  # This will make getattr return None

        mock_bedrock_client = AsyncMock()
        mock_response_body = Mock()
        mock_response_body.read.return_value = json.dumps({"completion": "test response"}).encode()
        mock_bedrock_client.__aenter__.return_value.invoke_model.return_value = {
            "body": mock_response_body
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            await self.invoke_route.endpoint(
                model_id="claude-v2", request=mock_request, bedrock_client=mock_bedrock_client
            )

        # Verify content type headers
        call_args = mock_bedrock_client.__aenter__.return_value.invoke_model.call_args[1]
        assert call_args["contentType"] == "application/json"
        assert call_args["accept"] == "application/json"
