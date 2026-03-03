"""Unit tests for main module."""

from unittest.mock import Mock, patch

from fastapi import APIRouter, FastAPI
from main import create_app


class TestMainApp:
    """Test cases for main application creation."""

    @patch("main.setup_telemetry")
    @patch("main.boto3.Session")
    @patch("main.BedrockService")
    @patch("main.GuardrailService")
    @patch("main.setup_general_routes")
    @patch("main.create_bedrock_router")
    @patch("main.create_global_exception_handler")
    @patch("main.instrument_app")
    def test_create_app_returns_fastapi_instance(
        self,
        _mock_instrument_app,
        mock_create_exception_handler,
        mock_create_bedrock_router,
        mock_setup_general_routes,
        _mock_guardrail_service,
        mock_bedrock_service,
        mock_boto3_session,
        mock_setup_telemetry,
    ):
        """Test that create_app returns a FastAPI instance."""
        # Mock telemetry setup
        mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        mock_setup_telemetry.return_value = mock_telemetry

        # Mock other dependencies
        mock_session = Mock()
        mock_boto3_session.return_value = mock_session

        mock_service = Mock()
        mock_bedrock_service.return_value = mock_service

        mock_router = APIRouter()
        mock_setup_general_routes.return_value = mock_router
        mock_create_bedrock_router.return_value = mock_router

        mock_exception_handler = Mock()
        mock_create_exception_handler.return_value = mock_exception_handler

        app = create_app()

        assert isinstance(app, FastAPI)
        assert app.title == "Sample Bedrock Proxy Gateway"
        assert app.description == "Lightweight managed proxy for Amazon Bedrock APIs"

    @patch("main.setup_telemetry")
    @patch("main.boto3.Session")
    @patch("main.BedrockService")
    @patch("main.GuardrailService")
    @patch("main.setup_general_routes")
    @patch("main.create_bedrock_router")
    @patch("main.create_global_exception_handler")
    @patch("main.instrument_app")
    def test_create_app_initializes_dependencies(
        self,
        _mock_instrument_app,
        _mock_create_exception_handler,
        mock_create_bedrock_router,
        mock_setup_general_routes,
        mock_guardrail_service,
        mock_bedrock_service,
        mock_boto3_session,
        mock_setup_telemetry,
    ):
        """Test that create_app initializes all dependencies correctly."""
        # Mock telemetry setup
        mock_telemetry = {
            "tracer": Mock(),
            "meter": Mock(),
            "logger": Mock(),
        }
        mock_setup_telemetry.return_value = mock_telemetry

        # Mock other dependencies
        mock_session = Mock()
        mock_boto3_session.return_value = mock_session

        mock_service = Mock()
        mock_bedrock_service.return_value = mock_service

        mock_router = APIRouter()
        mock_setup_general_routes.return_value = mock_router
        mock_create_bedrock_router.return_value = mock_router

        create_app()

        # Verify telemetry setup
        mock_setup_telemetry.assert_called_once()

        # Verify session creation
        mock_boto3_session.assert_called_once()

        # Verify Bedrock service creation
        mock_bedrock_service.assert_called_once_with(mock_session, mock_telemetry["logger"])

        # Verify guardrail service creation
        mock_guardrail_service.assert_called_once()

    def test_app_instance_exists(self):
        """Test that app instance is created at module level."""
        from main import app

        assert isinstance(app, FastAPI)
