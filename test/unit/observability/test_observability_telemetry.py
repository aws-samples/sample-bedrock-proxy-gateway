# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for observability.telemetry module."""

from unittest.mock import Mock, patch

from observability.telemetry import instrument_app, setup_telemetry


class TestTelemetry:
    """Test cases for telemetry setup and instrumentation."""

    @patch("observability.telemetry.config")
    def test_setup_telemetry_disabled(self, mock_config):
        """Test telemetry setup when OTEL is disabled."""
        mock_config.otel_sdk_disabled = True

        result = setup_telemetry()

        assert "tracer" in result
        assert "meter" in result
        assert "logger" in result

        # Should return no-op instances when disabled
        from opentelemetry import trace

        assert isinstance(result["tracer"], trace.NoOpTracer)

    @patch("observability.telemetry.config")
    @patch("observability.telemetry.trace")
    @patch("observability.telemetry.metrics")
    @patch("observability.telemetry.set_logger_provider")
    @patch("observability.telemetry.logging")
    @patch("observability.telemetry.LoggingInstrumentor")
    @patch("observability.telemetry.LoggingHandler")
    @patch("observability.telemetry.TracerProvider")
    @patch("observability.telemetry.MeterProvider")
    @patch("observability.telemetry.LoggerProvider")
    def test_setup_telemetry_enabled(
        self,
        _mock_logger_provider_class,
        _mock_meter_provider_class,
        _mock_tracer_provider_class,
        _mock_logging_handler,
        _mock_logging_instrumentor,
        mock_logging,
        _mock_set_logger_provider,
        mock_metrics,
        mock_trace,
        mock_config,
    ):
        """Test telemetry setup when OTEL is enabled."""
        mock_config.otel_sdk_disabled = False
        mock_config.otel_service_name = "test-service"
        mock_config.environment = "test"
        mock_config.otel_exporter_otlp_endpoint = "http://test:4317"
        mock_config.app_hash = "test-hash"
        mock_config.log_level = "INFO"

        # Mock logging constants
        mock_logging.INFO = 20
        mock_logging.getLogger.return_value = Mock()

        # Mock telemetry components
        mock_tracer = Mock()
        mock_meter = Mock()
        mock_logger = Mock()

        mock_trace.get_tracer.return_value = mock_tracer
        mock_metrics.get_meter.return_value = mock_meter

        with patch("observability.telemetry.ContextLogger") as mock_context_logger:
            mock_context_logger.return_value = mock_logger

            result = setup_telemetry()

        assert result["tracer"] == mock_tracer
        assert result["meter"] == mock_meter
        assert result["logger"] == mock_logger

    @patch("observability.telemetry.FastAPIInstrumentor")
    @patch("observability.telemetry.BotocoreInstrumentor")
    @patch("observability.telemetry.RequestsInstrumentor")
    @patch("observability.telemetry.URLLib3Instrumentor")
    def test_instrument_app(
        self,
        mock_urllib3_instrumentor,
        mock_requests_instrumentor,
        mock_botocore_instrumentor,
        mock_fastapi_instrumentor,
    ):
        """Test application instrumentation."""
        mock_app = Mock()

        instrument_app(mock_app)

        # Verify all instrumentors are called
        mock_fastapi_instrumentor.instrument_app.assert_called_once()
        mock_botocore_instrumentor.return_value.instrument.assert_called_once()
        mock_requests_instrumentor.return_value.instrument.assert_called_once()
        mock_urllib3_instrumentor.return_value.instrument.assert_called_once()

    @patch("observability.telemetry.config")
    def test_setup_telemetry_with_app_hash(self, mock_config):
        """Test telemetry setup includes app hash in resource attributes."""
        mock_config.otel_sdk_disabled = False
        mock_config.otel_service_name = "test-service"
        mock_config.environment = "test"
        mock_config.otel_exporter_otlp_endpoint = "http://localhost:4317"
        mock_config.app_hash = "abc123"
        mock_config.log_level = "INFO"

        with (
            patch("observability.telemetry.Resource") as mock_resource,
            patch("observability.telemetry.TracerProvider"),
            patch("observability.telemetry.MeterProvider"),
            patch("observability.telemetry.LoggerProvider"),
        ):
            setup_telemetry()

        # Verify resource includes deployment ID
        resource_call = mock_resource.create.call_args[0][0]
        assert resource_call["deployment.id"] == "abc123"

    def test_fastapi_instrumentation_no_hooks(self):
        """Test FastAPI instrumentation is called without custom hooks."""
        # Import the function directly to avoid recursion
        import observability.telemetry as telemetry_module

        # Create a mock app and call instrument_app
        mock_app = Mock()

        with (
            patch.object(telemetry_module, "FastAPIInstrumentor") as mock_fastapi,
            patch.object(telemetry_module, "BotocoreInstrumentor") as mock_botocore,
            patch.object(telemetry_module, "RequestsInstrumentor") as mock_requests,
            patch.object(telemetry_module, "URLLib3Instrumentor") as mock_urllib3,
            patch.object(telemetry_module, "SystemMetricsInstrumentor") as mock_system,
        ):
            # Configure mocks to return mock instances
            mock_botocore.return_value = Mock()
            mock_requests.return_value = Mock()
            mock_urllib3.return_value = Mock()
            mock_system.return_value = Mock()

            telemetry_module.instrument_app(mock_app)

            # Verify FastAPI instrumentation is called with app only
            mock_fastapi.instrument_app.assert_called_once_with(mock_app)

            # Verify no server_request_hook is passed (user context handled by TraceMiddleware)
            call_args = mock_fastapi.instrument_app.call_args
            assert len(call_args[0]) == 1  # Only app argument
            assert len(call_args[1]) == 0  # No keyword arguments

    def test_instrumentation_components_called(self):
        """Test all instrumentation components are properly initialized."""
        # Import the function directly to avoid recursion
        import observability.telemetry as telemetry_module

        # Create a mock app and call instrument_app
        mock_app = Mock()

        with (
            patch.object(telemetry_module, "FastAPIInstrumentor") as mock_fastapi,
            patch.object(telemetry_module, "BotocoreInstrumentor") as mock_botocore,
            patch.object(telemetry_module, "RequestsInstrumentor") as mock_requests,
            patch.object(telemetry_module, "URLLib3Instrumentor") as mock_urllib3,
            patch.object(telemetry_module, "SystemMetricsInstrumentor") as mock_system,
        ):
            # Configure mocks to return mock instances
            mock_botocore_instance = Mock()
            mock_requests_instance = Mock()
            mock_urllib3_instance = Mock()
            mock_system_instance = Mock()

            mock_botocore.return_value = mock_botocore_instance
            mock_requests.return_value = mock_requests_instance
            mock_urllib3.return_value = mock_urllib3_instance
            mock_system.return_value = mock_system_instance

            telemetry_module.instrument_app(mock_app)

            # Verify all instrumentors are called
            mock_fastapi.instrument_app.assert_called_once_with(mock_app)
            mock_botocore_instance.instrument.assert_called_once()
            mock_requests_instance.instrument.assert_called_once()
            mock_urllib3_instance.instrument.assert_called_once()
            mock_system_instance.instrument.assert_called_once()
