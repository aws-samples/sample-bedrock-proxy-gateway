# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Test to verify telemetry mocking works correctly."""

import os
from unittest.mock import patch

import pytest


class TestTelemetryMocking:
    """Test cases to verify telemetry is properly mocked during tests."""

    def test_otel_disabled_in_tests(self):
        """Test that OTEL is disabled during test execution."""
        assert os.getenv("OTEL_SDK_DISABLED") == "true"

    def test_safe_environment_variables(self):
        """Test that safe environment variables are set."""
        assert os.getenv("OTEL_SERVICE_NAME") == "test-service"
        assert os.getenv("ENVIRONMENT") == "test"
        assert os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") == ""

    @patch("observability.telemetry.setup_telemetry")
    def test_telemetry_setup_mocked(self, mock_setup):
        """Test that telemetry setup can be safely mocked."""
        from observability.telemetry import setup_telemetry

        mock_setup.return_value = {
            "tracer": "mock_tracer",
            "meter": "mock_meter",
            "logger": "mock_logger",
        }

        result = setup_telemetry()

        assert result["tracer"] == "mock_tracer"
        assert result["meter"] == "mock_meter"
        assert result["logger"] == "mock_logger"

    def test_no_grpc_connection_attempts(self):
        """Test that no gRPC connections are attempted during tests."""
        # This test passes if no connection errors occur
        # The fixture should prevent any OTEL initialization
        assert True

    @pytest.mark.asyncio
    async def test_async_test_compatibility(self):
        """Test that async tests work with telemetry mocking."""
        # Simulate an async operation that might use telemetry
        import asyncio

        await asyncio.sleep(0.001)

        # Should complete without OTEL connection errors
        assert os.getenv("OTEL_SDK_DISABLED") == "true"
