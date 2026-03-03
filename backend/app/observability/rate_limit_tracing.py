"""Rate limiting tracing utilities."""

from contextlib import asynccontextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)


@asynccontextmanager
async def rate_limit_span():
    """Create a tracing span for rate limiting middleware."""
    with tracer.start_as_current_span("rate_limit_middleware") as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
