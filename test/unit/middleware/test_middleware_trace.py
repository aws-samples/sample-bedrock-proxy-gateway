"""Unit tests for trace middleware."""

from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from middleware.trace import TraceMiddleware
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from starlette.responses import JSONResponse


@pytest.fixture
def setup_tracer():
    """Set up OpenTelemetry tracer for testing."""
    resource = Resource.create({"service.name": "test-service"})
    trace_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(trace_provider)
    return trace.get_tracer("test-service")


def test_trace_middleware_no_active_span():
    """Test that middleware handles case with no active span gracefully."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return JSONResponse({"message": "test"})

    client = TestClient(app)
    response = client.get("/test")

    assert response.status_code == 200
    # Should not have X-Trace-ID header when no active recording span
    assert "X-Trace-ID" not in response.headers


def test_trace_middleware_with_recording_span():
    """Test that middleware adds trace ID when there's an active recording span."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return JSONResponse({"message": "test"})

    # Mock trace.get_current_span to return a recording span
    with patch("middleware.trace.trace.get_current_span") as mock_get_span:
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span_context = Mock()
        mock_span_context.trace_id = 0x12345678901234567890123456789012
        mock_span.get_span_context.return_value = mock_span_context
        mock_get_span.return_value = mock_span

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        # Should have X-Trace-ID header when there's an active recording span
        assert "X-Trace-ID" in response.headers
        trace_id = response.headers["X-Trace-ID"]

        # Trace ID should be a 32-character hex string
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)
        # Should not be all zeros
        assert trace_id != "00000000000000000000000000000000"
        assert trace_id == "12345678901234567890123456789012"


def test_trace_middleware_with_non_recording_span():
    """Test that middleware doesn't add trace ID for non-recording spans."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return JSONResponse({"message": "test"})

    # Mock trace.get_current_span to return a non-recording span
    with patch("middleware.trace.trace.get_current_span") as mock_get_span:
        mock_span = Mock()
        mock_span.is_recording.return_value = False  # This is the key difference
        mock_get_span.return_value = mock_span

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        # Should not have X-Trace-ID header for non-recording spans
        assert "X-Trace-ID" not in response.headers


def test_trace_middleware_preserves_existing_trace_id():
    """Test that middleware doesn't override existing X-Trace-ID header."""
    existing_trace_id = "12345678901234567890123456789012"

    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        response = JSONResponse({"message": "test"})
        response.headers["X-Trace-ID"] = existing_trace_id
        return response

    # Mock trace.get_current_span to return a recording span
    with patch("middleware.trace.trace.get_current_span") as mock_get_span:
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span_context = Mock()
        mock_span_context.trace_id = 0x99999999999999999999999999999999
        mock_span.get_span_context.return_value = mock_span_context
        mock_get_span.return_value = mock_span

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        # Should preserve the existing trace ID
        assert response.headers["X-Trace-ID"] == existing_trace_id


def test_trace_middleware_with_context_variables():
    """Test that middleware sets span attributes from context variables."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return JSONResponse({"message": "test"})

    with (
        patch("middleware.trace.trace.get_current_span") as mock_get_span,
        patch("middleware.trace.client_id_context") as mock_client_id_ctx,
        patch("middleware.trace.client_name_context") as mock_client_name_ctx,
    ):
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_get_span.return_value = mock_span
        mock_client_id_ctx.get.return_value = "test-client-456"
        mock_client_name_ctx.get.return_value = "Test Client"

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        mock_span.set_attribute.assert_any_call("client.id", "test-client-456")
        mock_span.set_attribute.assert_any_call("client.name", "Test Client")


def test_trace_middleware_with_none_context_variables():
    """Test that middleware handles None context variables gracefully."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return JSONResponse({"message": "test"})

    with (
        patch("middleware.trace.trace.get_current_span") as mock_get_span,
        patch("middleware.trace.client_id_context") as mock_client_id_ctx,
        patch("middleware.trace.client_name_context") as mock_client_name_ctx,
    ):
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_get_span.return_value = mock_span
        mock_client_id_ctx.get.return_value = None
        mock_client_name_ctx.get.return_value = None

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        # Should not call set_attribute for None values
        mock_span.set_attribute.assert_not_called()
