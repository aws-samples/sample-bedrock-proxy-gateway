# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for main module."""

from unittest.mock import Mock, patch

from fastapi import APIRouter, FastAPI
from main import create_app


class TestMainApp:
    """Test cases for main application creation."""

    @patch("main.setup_telemetry")
    @patch("main.GuardrailService")
    @patch("main.BedrockHttpxService")
    @patch("main.setup_general_routes")
    @patch("main.create_bedrock_httpx_router")
    @patch("main.create_global_exception_handler")
    @patch("main.instrument_app")
    def test_create_app_returns_fastapi_instance(
        self,
        _mock_instrument_app,
        mock_create_exception_handler,
        mock_create_httpx_router,
        mock_setup_general_routes,
        _mock_httpx_service,
        _mock_guardrail_service,
        mock_setup_telemetry,
    ):
        """Test that create_app returns a FastAPI instance."""
        mock_setup_telemetry.return_value = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        mock_setup_general_routes.return_value = APIRouter()
        mock_create_httpx_router.return_value = APIRouter()
        mock_create_exception_handler.return_value = Mock()

        app = create_app()

        assert isinstance(app, FastAPI)
        assert app.title == "Sample Bedrock Proxy Gateway"

    @patch("main.setup_telemetry")
    @patch("main.GuardrailService")
    @patch("main.BedrockHttpxService")
    @patch("main.setup_general_routes")
    @patch("main.create_bedrock_httpx_router")
    @patch("main.create_global_exception_handler")
    @patch("main.instrument_app")
    def test_create_app_initializes_dependencies(
        self,
        _mock_instrument_app,
        _mock_create_exception_handler,
        mock_create_httpx_router,
        mock_setup_general_routes,
        mock_httpx_service,
        mock_guardrail_service,
        mock_setup_telemetry,
    ):
        """Test that create_app initializes all dependencies correctly."""
        mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        mock_setup_telemetry.return_value = mock_telemetry
        mock_setup_general_routes.return_value = APIRouter()
        mock_create_httpx_router.return_value = APIRouter()

        create_app()

        mock_setup_telemetry.assert_called_once()
        mock_guardrail_service.assert_called_once()
        mock_httpx_service.assert_called_once_with(mock_telemetry["logger"])

    def test_app_instance_exists(self):
        """Test that app instance is created at module level."""
        from main import app

        assert isinstance(app, FastAPI)
