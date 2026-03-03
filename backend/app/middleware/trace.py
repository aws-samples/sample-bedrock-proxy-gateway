"""Trace ID middleware module."""

# Import context variables from context_vars to avoid duplication
from observability.context_vars import client_id_context, client_name_context
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware


class TraceMiddleware(BaseHTTPMiddleware):
    """Middleware to add trace ID to all responses.

    This middleware ensures that all responses, including those from public endpoints
    that bypass authentication, include the trace ID in the response headers.
    """

    def __init__(self, app):
        """Initialize trace middleware.

        Args:
        ----
            app: FastAPI application instance.
        """
        super().__init__(app)

    async def dispatch(self, request, call_next):
        """Process request through trace middleware.

        Adds trace ID to response headers for all requests.

        Args:
        ----
            request: Incoming HTTP request.
            call_next: Next middleware or route handler in the chain.

        Returns:
        -------
            Response: HTTP response with trace ID header added.
        """
        # Get the current span
        current_span = trace.get_current_span()

        # Get user context from context variables
        client_id = client_id_context.get()
        client_name = client_name_context.get()

        # Set attributes on the current span with consistent naming
        if client_id:
            current_span.set_attribute("client.id", client_id)
        if client_name:
            current_span.set_attribute("client.name", client_name)

        # Process the request through the rest of the application
        response = await call_next(request)

        # Add trace ID to response headers if not already present
        if "X-Trace-ID" not in response.headers:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                trace_id = format(current_span.get_span_context().trace_id, "032x")
                response.headers["X-Trace-ID"] = trace_id

        return response
