"""OpenTelemetry configuration module."""

import logging

from config import config
from observability.context_logger import ContextLogger
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _setup_valkey_glide_telemetry():
    """Initialize OpenTelemetry for valkey-glide client."""
    try:
        from glide import (
            OpenTelemetry,
            OpenTelemetryConfig,
            OpenTelemetryMetricsConfig,
            OpenTelemetryTracesConfig,
        )

        otel_config = OpenTelemetryConfig(
            traces=OpenTelemetryTracesConfig(
                endpoint=f"{config.otel_exporter_otlp_endpoint}/v1/traces",
                sample_percentage=1,  # 1% sampling
            ),
            metrics=OpenTelemetryMetricsConfig(
                endpoint=f"{config.otel_exporter_otlp_endpoint}/v1/metrics"
            ),
            flush_interval_ms=5000,
        )
        OpenTelemetry.init(otel_config)
    except Exception:  # nosec B110
        # Silently fail if already initialized or glide not available
        pass


def setup_telemetry():
    """Configure OpenTelemetry tracing, metrics, and logging.

    Returns
    -------
        dict: Dictionary containing tracer, meter, and logger instances.
    """
    # Check if OpenTelemetry is disabled
    if config.otel_sdk_disabled:
        return {
            "tracer": trace.NoOpTracer(),
            "meter": metrics.NoOpMeter("disabled"),
            "logger": ContextLogger(logging.getLogger("bedrock-gateway")),
        }

    # Initialize valkey-glide telemetry
    _setup_valkey_glide_telemetry()

    # Environment-based configuration for observability
    service_name = config.otel_service_name
    environment = config.environment
    endpoint = config.otel_exporter_otlp_endpoint

    # Resource attributes help identify this service in observability platforms
    # The collector can enrich these with additional metadata (host, ecs info, etc.)
    resource_attrs = {
        "service.name": service_name,
        "service.namespace": "api",
        "deployment.environment": environment,
    }

    # Add app_hash as deployment ID if available
    if config.app_hash:
        resource_attrs["deployment.id"] = config.app_hash

    resource = Resource.create(resource_attrs)

    # Configure distributed tracing with batch processing for performance
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(trace_provider)

    # Configure metrics with longer export interval to reduce collector load
    # Batch processing reduces network overhead and improves performance
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=60000,  # 60 seconds to match collector batch
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Configure structured logging with trace correlation
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(logger_provider)

    # Bridge Python's standard logging to OpenTelemetry
    log_level = getattr(logging, config.log_level)
    otlp_handler = LoggingHandler(level=log_level, logger_provider=logger_provider)

    # Configure root logger to capture ALL Python logging (including dependencies)
    # This ensures comprehensive log collection across the entire application
    logging.basicConfig(level=log_level, handlers=[otlp_handler], force=True)

    # Add trace context to logs for correlation between traces and logs
    # This enables powerful debugging by linking logs to specific requests
    LoggingInstrumentor().instrument(
        set_logging_format=True,
        logger_provider=logger_provider,
        tracer_provider=trace_provider,
    )

    return {
        "tracer": trace.get_tracer(service_name),
        "meter": metrics.get_meter(service_name),
        "logger": ContextLogger(logging.getLogger(service_name)),
    }


def instrument_app(app):
    """Instrument FastAPI app and boto3.

    Args:
    ----
        app: FastAPI application instance to instrument.
    """
    # Auto-instrument FastAPI
    # Note: User context is added by TraceMiddleware using context variables
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument AWS SDK calls for complete request tracing
    BotocoreInstrumentor().instrument()

    # Auto-instrument HTTP client libraries for external API calls
    RequestsInstrumentor().instrument()
    URLLib3Instrumentor().instrument()

    # Auto-instrument system metrics for resource monitoring
    SystemMetricsInstrumentor().instrument()
