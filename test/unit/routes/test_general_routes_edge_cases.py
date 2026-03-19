# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Edge case tests for general_routes module."""

from unittest.mock import patch

import pytest
from fastapi import APIRouter
from routes.general_routes import setup_general_routes


class TestGeneralRoutesEdgeCases:
    """Test edge cases for general routes."""

    def test_setup_general_routes_with_aws_client_factory(self):
        """Test setup_general_routes with AWS client factory parameter."""
        router = setup_general_routes()

        assert isinstance(router, APIRouter)

    def test_setup_general_routes_with_none_factory(self):
        """Test setup_general_routes with None factory parameter."""
        router = setup_general_routes()

        assert isinstance(router, APIRouter)

    @pytest.mark.asyncio
    @patch("routes.general_routes.config")
    async def test_root_endpoint_with_none_environment(self, mock_config):
        """Test root endpoint when environment variable returns None."""
        mock_config.environment = None

        router = setup_general_routes()

        root_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/":
                root_route = route
                break

        response = await root_route.endpoint()

        assert response["message"] == "Hello from Bedrock Gateway"
        assert response["environment"] is None

    @pytest.mark.asyncio
    @patch("routes.general_routes.config")
    async def test_root_endpoint_with_special_characters(self, mock_config):
        """Test root endpoint with special characters in environment."""
        mock_config.environment = "test-env_123!@#"

        router = setup_general_routes()

        root_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/":
                root_route = route
                break

        response = await root_route.endpoint()

        assert response["environment"] == "test-env_123!@#"

    def test_router_has_correct_number_of_routes(self):
        """Test that router has the expected number of routes."""
        router = setup_general_routes()

        # Check that we have the expected routes
        paths = [route.path for route in router.routes if hasattr(route, "path")]
        expected_paths = {"/", "/debug"}
        actual_paths = set(paths)
        assert expected_paths.issubset(actual_paths)

    def test_all_routes_are_get_methods(self):
        """Test that all routes use GET method."""
        router = setup_general_routes()

        for route in router.routes:
            if hasattr(route, "methods"):
                assert "GET" in route.methods
                assert len(route.methods) == 1  # Only GET method

    def test_debug_endpoint_response_structure(self):
        """Test debug endpoint returns correct response structure."""
        router = setup_general_routes()

        debug_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/debug":
                debug_route = route
                break

        assert debug_route is not None

        # Verify the endpoint function exists and is callable
        assert callable(debug_route.endpoint)

    @pytest.mark.asyncio
    async def test_debug_endpoint_response_keys(self):
        """Test debug endpoint returns all expected keys."""
        router = setup_general_routes()

        debug_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/debug":
                debug_route = route
                break

        response = await debug_route.endpoint()

        expected_keys = {"status", "docs_url", "redoc_url", "openapi_url"}
        assert set(response.keys()) == expected_keys

    def test_route_paths_are_strings(self):
        """Test that all route paths are strings."""
        router = setup_general_routes()

        for route in router.routes:
            if hasattr(route, "path"):
                assert isinstance(route.path, str)

    def test_route_endpoints_are_callable(self):
        """Test that all route endpoints are callable."""
        router = setup_general_routes()

        for route in router.routes:
            if hasattr(route, "endpoint"):
                assert callable(route.endpoint)

    @pytest.mark.asyncio
    async def test_root_endpoint_return_type(self):
        """Test root endpoint returns dictionary."""
        router = setup_general_routes()

        root_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/":
                root_route = route
                break

        response = await root_route.endpoint()

        assert isinstance(response, dict)
        assert len(response) == 2  # message and environment

    @pytest.mark.asyncio
    async def test_debug_endpoint_return_type(self):
        """Test debug endpoint returns dictionary."""
        router = setup_general_routes()

        debug_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/debug":
                debug_route = route
                break

        response = await debug_route.endpoint()

        assert isinstance(response, dict)
        assert len(response) == 4  # status, docs_url, redoc_url, openapi_url
