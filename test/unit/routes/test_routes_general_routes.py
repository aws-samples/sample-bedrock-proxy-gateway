"""Unit tests for routes.general_routes module."""

from unittest.mock import patch

import pytest
from fastapi import APIRouter
from routes.general_routes import setup_general_routes


class TestGeneralRoutes:
    """Test cases for general routes setup and endpoints."""

    def test_setup_general_routes_returns_router(self):
        """Test that setup_general_routes returns an APIRouter."""
        router = setup_general_routes()

        assert isinstance(router, APIRouter)

    @pytest.mark.asyncio
    @patch("routes.general_routes.config")
    async def test_root_endpoint(self, mock_config):
        """Test root endpoint functionality."""
        mock_config.environment = "test"

        router = setup_general_routes()

        # Find the root endpoint
        root_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/":
                root_route = route
                break

        assert root_route is not None

        # Call the endpoint function directly
        response = await root_route.endpoint()

        assert response["message"] == "Hello from Bedrock Gateway"
        assert response["environment"] == "test"

    @pytest.mark.asyncio
    @patch("routes.general_routes.config")
    async def test_root_endpoint_no_environment(self, mock_config):
        """Test root endpoint with no environment variable."""
        mock_config.environment = ""

        router = setup_general_routes()

        # Find the root endpoint
        root_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/":
                root_route = route
                break

        response = await root_route.endpoint()

        assert response["message"] == "Hello from Bedrock Gateway"
        assert response["environment"] == ""

    @pytest.mark.asyncio
    async def test_debug_endpoint(self):
        """Test debug endpoint functionality."""
        router = setup_general_routes()

        # Find the debug endpoint
        debug_route = None
        for route in router.routes:
            if hasattr(route, "path") and route.path == "/debug":
                debug_route = route
                break

        assert debug_route is not None

        # Call the endpoint function directly
        response = await debug_route.endpoint()

        expected_response = {
            "status": "ok",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
        }

        assert response == expected_response

    def test_routes_configuration(self):
        """Test that routes are properly configured."""
        router = setup_general_routes()

        # Check that we have the expected routes
        paths = [route.path for route in router.routes if hasattr(route, "path")]

        assert "/" in paths
        assert "/debug" in paths

    def test_routes_exclude_from_schema(self):
        """Test that routes are excluded from OpenAPI schema."""
        router = setup_general_routes()

        for route in router.routes:
            if hasattr(route, "include_in_schema"):
                assert route.include_in_schema is False

    def test_routes_methods(self):
        """Test that routes use correct HTTP methods."""
        router = setup_general_routes()

        for route in router.routes:
            if hasattr(route, "methods"):
                assert "GET" in route.methods

    @pytest.mark.asyncio
    @patch("routes.general_routes.config")
    async def test_root_endpoint_different_environments(self, mock_config):
        """Test root endpoint with different environment values."""
        environments = ["dev", "prod", "staging", "local"]

        for env in environments:
            mock_config.environment = env

            router = setup_general_routes()
            root_route = None
            for route in router.routes:
                if hasattr(route, "path") and route.path == "/":
                    root_route = route
                    break

            response = await root_route.endpoint()

            assert response["environment"] == env
            assert response["message"] == "Hello from Bedrock Gateway"

    def test_setup_with_bedrock_service(self):
        """Test setup with bedrock service parameter."""
        router = setup_general_routes()

        assert isinstance(router, APIRouter)
        # Verify routes are still created
        paths = [route.path for route in router.routes if hasattr(route, "path")]
        assert len(paths) >= 2  # root, debug
