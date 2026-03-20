# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for common bedrock routes functionality."""

import base64
import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import APIRouter, HTTPException
from routes.bedrock_routes import create_bedrock_router
from services.bedrock_service import BedrockService


class TestBedrockCommon:
    """Test class for common bedrock routes functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_bedrock_service = Mock(spec=BedrockService)
        self.mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        self.router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

    def test_bedrock_router_creation(self):
        """Test that bedrock router is properly created."""
        router = create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)
        assert isinstance(router, APIRouter)

    def test_router_has_expected_routes(self):
        """Test that all expected routes are configured."""
        route_info = []
        for route in self.router.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                route_info.append((route.path, list(route.methods)))

        expected_routes = [
            ("/model/{model_id}/converse", ["POST"]),
            ("/model/{model_id}/converse-stream", ["POST"]),
            ("/model/{model_id}/invoke", ["POST"]),
            ("/model/{model_id}/invoke-with-response-stream", ["POST"]),
            ("/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply", ["POST"]),
        ]

        for expected_path, expected_methods in expected_routes:
            matching_routes = [
                (path, methods) for path, methods in route_info if path == expected_path
            ]
            assert len(matching_routes) == 1, f"Route {expected_path} not found or duplicated"
            assert expected_methods[0] in matching_routes[0][1], (
                f"Method {expected_methods[0]} not found for {expected_path}"
            )

    def test_router_dependencies(self):
        """Test that routes have proper dependencies."""
        for route in self.router.routes:
            if hasattr(route, "dependant") and route.dependant:
                # Each route should have at least one dependency (the bedrock client)
                assert len(route.dependant.dependencies) >= 1

    @patch("routes.bedrock_routes.MetricsCollector")
    def test_metrics_collector_initialization(self, mock_metrics_class):
        """Test that MetricsCollector is properly initialized."""
        mock_metrics = Mock()
        mock_metrics_class.return_value = mock_metrics

        create_bedrock_router(self.mock_bedrock_service, self.mock_telemetry)

        mock_metrics_class.assert_called_with(
            self.mock_telemetry["meter"],
            self.mock_telemetry["tracer"],
            self.mock_telemetry["logger"],
        )

    def test_telemetry_components_extraction(self):
        """Test that telemetry components are properly extracted."""
        mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }

        with patch("routes.bedrock_routes.MetricsCollector") as mock_metrics_class:
            create_bedrock_router(Mock(), mock_telemetry)

            call_args = mock_metrics_class.call_args[0]
            assert call_args[0] == mock_telemetry["meter"]
            assert call_args[1] == mock_telemetry["tracer"]
            assert call_args[2] == mock_telemetry["logger"]

    def test_decode_base64_bytes_function(self):
        """Test the decode_base64_bytes helper function."""
        router = create_bedrock_router(
            Mock(), {"tracer": Mock(), "meter": Mock(), "logger": Mock()}
        )

        # Get the decode function from the router's closure
        decode_func = None
        for route in router.routes:
            if hasattr(route, "endpoint"):
                closure_vars = route.endpoint.__code__.co_freevars
                if "decode_base64_bytes" in closure_vars:
                    decode_func = route.endpoint.__closure__[
                        closure_vars.index("decode_base64_bytes")
                    ].cell_contents
                    break

        assert decode_func is not None

        # Test data with base64 encoded bytes
        test_data = {
            "messages": [
                {
                    "content": [
                        {"text": "Hello"},
                        {"image": {"bytes": base64.b64encode(b"test image data").decode()}},
                    ]
                }
            ]
        }

        decode_func(test_data)

        # Verify bytes were decoded
        assert test_data["messages"][0]["content"][1]["image"]["bytes"] == b"test image data"

    def test_decode_base64_bytes_nested_structures(self):
        """Test decode_base64_bytes with nested structures."""
        router = create_bedrock_router(
            Mock(), {"tracer": Mock(), "meter": Mock(), "logger": Mock()}
        )

        decode_func = None
        for route in router.routes:
            if hasattr(route, "endpoint"):
                closure_vars = route.endpoint.__code__.co_freevars
                if "decode_base64_bytes" in closure_vars:
                    decode_func = route.endpoint.__closure__[
                        closure_vars.index("decode_base64_bytes")
                    ].cell_contents
                    break

        # Test with list containing nested objects
        test_data = [
            {"bytes": base64.b64encode(b"data1").decode()},
            {"nested": {"bytes": base64.b64encode(b"data2").decode()}},
        ]

        decode_func(test_data)

        assert test_data[0]["bytes"] == b"data1"
        assert test_data[1]["nested"]["bytes"] == b"data2"

    def test_decode_base64_bytes_non_bytes_key(self):
        """Test decode_base64_bytes with non-bytes keys."""
        router = create_bedrock_router(
            Mock(), {"tracer": Mock(), "meter": Mock(), "logger": Mock()}
        )

        decode_func = None
        for route in router.routes:
            if hasattr(route, "endpoint"):
                closure_vars = route.endpoint.__code__.co_freevars
                if "decode_base64_bytes" in closure_vars:
                    decode_func = route.endpoint.__closure__[
                        closure_vars.index("decode_base64_bytes")
                    ].cell_contents
                    break

        # Test with data that has no bytes keys
        test_data = {"text": "hello", "number": 42, "nested": {"value": "test"}}
        original_data = test_data.copy()

        decode_func(test_data)

        # Data should remain unchanged
        assert test_data == original_data

    @pytest.mark.asyncio
    async def test_get_bedrock_client_missing_token(self):
        """Test get_bedrock_client with missing authorization token."""
        # Find any route to get the dependency
        converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                converse_route = route
                break

        get_bedrock_client = None
        for dep in converse_route.dependant.dependencies:
            if dep.call.__name__ == "get_bedrock_client":
                get_bedrock_client = dep.call
                break

        assert get_bedrock_client is not None

        mock_request = Mock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_bedrock_client(mock_request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["Error"]["Code"] == "AccessDenied"
        assert exc_info.value.detail["Error"]["Message"] == "Invalid Token"

    @pytest.mark.asyncio
    async def test_get_bedrock_client_invalid_token(self):
        """Test get_bedrock_client with invalid token."""
        converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                converse_route = route
                break

        get_bedrock_client = None
        for dep in converse_route.dependant.dependencies:
            if dep.call.__name__ == "get_bedrock_client":
                get_bedrock_client = dep.call
                break

        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer invalid-token"}

        self.mock_bedrock_service.get_authenticated_client = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_bedrock_client(mock_request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["Error"]["Code"] == "AccessDenied"
        assert exc_info.value.detail["Error"]["Message"] == "Invalid Token"

    @pytest.mark.asyncio
    async def test_get_bedrock_client_success(self):
        """Test successful bedrock client creation."""
        converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                converse_route = route
                break

        get_bedrock_client = None
        for dep in converse_route.dependant.dependencies:
            if dep.call.__name__ == "get_bedrock_client":
                get_bedrock_client = dep.call
                break

        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer valid-token"}
        mock_client = Mock()
        self.mock_bedrock_service.get_authenticated_client = AsyncMock(return_value=mock_client)

        result = await get_bedrock_client(mock_request)
        assert result == mock_client

    @pytest.mark.asyncio
    async def test_get_bedrock_client_with_rate_ctx(self):
        """Test get_bedrock_client with rate limiting context."""
        converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                converse_route = route
                break

        get_bedrock_client = None
        for dep in converse_route.dependant.dependencies:
            if dep.call.__name__ == "get_bedrock_client":
                get_bedrock_client = dep.call
                break

        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer valid-token"}
        mock_request.state.rate_ctx = ("client_id", "model_id", "account_id", 1000, "api_type")
        mock_client = Mock()
        self.mock_bedrock_service.get_authenticated_client = AsyncMock(return_value=mock_client)

        result = await get_bedrock_client(mock_request)
        assert result == mock_client
        # Verify account_id was extracted and passed
        self.mock_bedrock_service.get_authenticated_client.assert_called_with(
            "valid-token", "account_id"
        )

    @pytest.mark.asyncio
    async def test_get_bedrock_client_invalid_rate_ctx(self):
        """Test get_bedrock_client with invalid rate context."""
        converse_route = None
        for route in self.router.routes:
            if hasattr(route, "path") and route.path == "/model/{model_id}/converse":
                converse_route = route
                break

        get_bedrock_client = None
        for dep in converse_route.dependant.dependencies:
            if dep.call.__name__ == "get_bedrock_client":
                get_bedrock_client = dep.call
                break

        mock_request = Mock()
        mock_request.headers = {"Authorization": "Bearer valid-token"}
        mock_request.state.rate_ctx = "invalid_tuple"  # Not a tuple
        mock_client = Mock()
        self.mock_bedrock_service.get_authenticated_client = AsyncMock(return_value=mock_client)

        result = await get_bedrock_client(mock_request)
        assert result == mock_client
        # Verify None was passed as account_id due to invalid rate_ctx
        self.mock_bedrock_service.get_authenticated_client.assert_called_with("valid-token", None)

    def test_router_route_count(self):
        """Test that router has the expected number of routes."""
        assert len(self.router.routes) == 5

    def test_decode_base64_bytes_with_invalid_base64(self):
        """Test decode_base64_bytes with invalid base64 data."""
        router = create_bedrock_router(
            Mock(), {"tracer": Mock(), "meter": Mock(), "logger": Mock()}
        )

        decode_func = None
        for route in router.routes:
            if hasattr(route, "endpoint"):
                closure_vars = route.endpoint.__code__.co_freevars
                if "decode_base64_bytes" in closure_vars:
                    decode_func = route.endpoint.__closure__[
                        closure_vars.index("decode_base64_bytes")
                    ].cell_contents
                    break

        # Test with invalid base64 data - should not crash
        test_data = {"bytes": "invalid_base64!@#"}

        # This should not raise an exception, but may leave data unchanged
        with contextlib.suppress(Exception):
            decode_func(test_data)
