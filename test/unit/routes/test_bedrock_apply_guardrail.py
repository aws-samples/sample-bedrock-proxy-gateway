# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for bedrock apply guardrail API endpoint."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from botocore.exceptions import ClientError, ParamValidationError
from fastapi import HTTPException
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockApplyGuardrail:
    """Test class for bedrock apply guardrail API functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        # Find the apply guardrail route
        self.guardrail_route = None
        for route in self.router.routes:
            if (
                hasattr(route, "path")
                and route.path
                == "/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply"
            ):
                self.guardrail_route = route
                break

    @pytest.mark.asyncio
    async def test_apply_guardrail_success(self):
        """Test successful apply guardrail API call."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={
                "content": [{"text": "test content"}],
                "outputScope": "FULL",
                "source": "INPUT",
            }
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.return_value = {
            "action": "NONE",
            "outputs": [{"text": "test content"}],
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert result["action"] == "NONE"
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_guardrail_no_resolved_guardrail(self):
        """Test apply guardrail with no resolved guardrail."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        # Ensure request.state doesn't have resolved_guardrail
        mock_request.state = Mock()
        del mock_request.state.resolved_guardrail  # This will make getattr return None

        mock_bedrock_client = AsyncMock()

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 404
        assert "Guardrail 'logical-id' not found" in exc_info.value.detail["Error"]["Message"]

    @pytest.mark.asyncio
    async def test_apply_guardrail_with_optional_fields(self):
        """Test apply guardrail with optional fields."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={
                "content": [{"text": "test content"}],
                "outputScope": "INTERVENTIONS",
                "source": "OUTPUT",
            }
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "2",
        }

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.return_value = {
            "action": "BLOCKED",
            "outputs": [{"text": "blocked content"}],
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert result["action"] == "BLOCKED"
        # Verify optional parameters were passed
        call_args = mock_bedrock_client.__aenter__.return_value.apply_guardrail.call_args[1]
        assert call_args["outputScope"] == "INTERVENTIONS"
        assert call_args["source"] == "OUTPUT"

    @pytest.mark.asyncio
    async def test_apply_guardrail_client_error(self):
        """Test apply guardrail with ClientError."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "ValidationException", "Message": "Invalid content"},
            "ResponseMetadata": {"HTTPStatusCode": 400},
        }
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.side_effect = ClientError(
            error_response, "ApplyGuardrail"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_apply_guardrail_client_error_empty_message(self):
        """Test apply guardrail with ClientError having empty message."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        error_response = {
            "Error": {"Code": "AccessDeniedException", "Message": ""},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        }
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.side_effect = ClientError(
            error_response, "ApplyGuardrail"
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 403
        assert (
            "Bedrock API error: AccessDeniedException" in exc_info.value.detail["Error"]["Message"]
        )

    @pytest.mark.asyncio
    async def test_apply_guardrail_param_validation_error(self):
        """Test apply guardrail with ParamValidationError."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.side_effect = (
            ParamValidationError(report="Invalid guardrail ID")
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.guardrail_route.endpoint(
                guardrail_identifier="invalid-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_apply_guardrail_general_exception(self):
        """Test apply guardrail with general exception."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.side_effect = Exception(
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
            await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_apply_guardrail_http_exception_passthrough(self):
        """Test that HTTPException is passed through unchanged."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={"content": [{"text": "test content"}], "source": "INPUT"}
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        original_exception = HTTPException(status_code=429, detail="Rate limited")
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.side_effect = (
            original_exception
        )

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with (
            patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics),
            pytest.raises(HTTPException) as exc_info,
        ):
            await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limited"

    @pytest.mark.asyncio
    async def test_apply_guardrail_multiple_content_items(self):
        """Test apply guardrail with multiple content items."""
        mock_request = Mock()
        mock_request.json = AsyncMock(
            return_value={
                "content": [
                    {"text": "first content"},
                    {"text": "second content"},
                    {"image": {"format": "png", "source": {"bytes": b"image_data"}}},
                ],
                "source": "INPUT",
            }
        )
        mock_request.state.resolved_guardrail = {
            "guardrailIdentifier": "actual-guardrail-id",
            "guardrailVersion": "1",
        }

        mock_bedrock_client = AsyncMock()
        mock_bedrock_client.__aenter__.return_value.apply_guardrail.return_value = {
            "action": "NONE",
            "outputs": [
                {"text": "first content"},
                {"text": "second content"},
                {"image": {"format": "png", "source": {"bytes": b"image_data"}}},
            ],
        }

        mock_metrics = Mock()
        mock_metrics.track_request = AsyncMock()
        mock_metrics.track_request.return_value.__aenter__ = AsyncMock()
        mock_metrics.track_request.return_value.__aexit__ = AsyncMock()

        with patch("routes.bedrock_routes.MetricsCollector", return_value=mock_metrics):
            result = await self.guardrail_route.endpoint(
                guardrail_identifier="logical-id",
                guardrail_version="DRAFT",
                request=mock_request,
                bedrock_client=mock_bedrock_client,
            )

        assert len(result["outputs"]) == 3
        assert result["action"] == "NONE"
