"""Authentication middleware module."""

import logging

from core.auth.jwt_validator import validate_jwt_claims, validate_jwt_token
from fastapi import HTTPException, Request
from observability.context_vars import clear_user_context, set_user_context
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from util.constants import PUBLIC_PATHS

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """JWT authentication middleware for FastAPI.

    Validates JWT tokens for all requests except public endpoints.
    Extracts user context from validated tokens and injects it into
    the request for downstream processing.
    """

    def __init__(self, app):
        """Initialize authentication middleware.

        Args:
        ----
            app: FastAPI application instance.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """Process request through authentication middleware.

        Validates JWT tokens and extracts user context for authenticated requests.
        Public endpoints bypass authentication entirely.

        Args:
        ----
            request: Incoming HTTP request.
            call_next: Next middleware or route handler in the chain.

        Returns:
        -------
            Response: HTTP response from downstream handler or error response.
        """
        # Skip authentication for public endpoints
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Extract and validate Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning("No Authorization header provided")
            from util.aws_error_response import create_aws_http_exception

            raise create_aws_http_exception(
                status_code=401,
                error_code="UnauthorizedOperation",
                error_message="Authorization header required",
                request_id="auth-missing-header",
            )

        # Ensure proper Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning("Invalid Authorization header format")
            from util.aws_error_response import create_aws_http_exception

            raise create_aws_http_exception(
                status_code=401,
                error_code="UnauthorizedOperation",
                error_message="Bearer token required",
                request_id="auth-invalid-format",
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Two-step JWT validation: signature/structure then business claims
            with tracer.start_as_current_span("authn.validate_token") as span:
                span.set_attribute("authn.method", "jwt")
                claims = validate_jwt_token(token)
                client_info = validate_jwt_claims(claims)
                span.set_attribute("authn.client_id", client_info["client_id"])

            # Set user context for logging and tracing
            set_user_context(client_info["client_id"], None, client_info.get("scope"))

            logger.debug(
                f"Authenticated client: {client_info['client_id']} with scope: {client_info['scope']}"
            )

            # Continue to the actual route handler
            response = await call_next(request)

            # Clear user context after request
            clear_user_context()
            return response

        except ValueError as e:
            logger.warning(f"JWT validation failed: {str(e)}")
            clear_user_context()
            from util.aws_error_response import create_aws_http_exception

            # Distinguish between authorization (403) and authentication (401) errors
            if "scope" in str(e).lower():
                raise create_aws_http_exception(
                    status_code=403,
                    error_code="AccessDenied",
                    error_message="Insufficient permissions",
                    request_id="auth-insufficient-scope",
                ) from e
            raise create_aws_http_exception(
                status_code=401,
                error_code="UnauthorizedOperation",
                error_message="Invalid or expired token",
                request_id="auth-invalid-token",
            ) from e
        except HTTPException:
            # Re-raise HTTPExceptions (like 429 rate limit errors) to preserve status codes
            clear_user_context()
            raise
        except Exception as e:
            # Catch-all for unexpected authentication errors
            logger.error(f"Authentication error: {type(e).__name__}: {str(e)}")
            clear_user_context()
            from util.aws_error_response import create_aws_http_exception

            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message="Authentication service error",
                request_id="auth-internal-error",
            ) from e
