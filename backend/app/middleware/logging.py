# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Request logging middleware module."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from util.constants import PUBLIC_PATHS

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request duration for non-public paths.

    This middleware logs the duration of requests in milliseconds for all paths
    that are not in the PUBLIC_PATHS list.
    """

    def __init__(self, app):
        """Initialize logging middleware.

        Args:
        ----
            app: FastAPI application instance.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        """Process request through logging middleware.

        Logs request duration for non-public paths.

        Args:
        ----
            request: Incoming HTTP request.
            call_next: Next middleware or route handler in the chain.

        Returns:
        -------
            Response: HTTP response from downstream handler.
        """
        # Skip logging for public endpoints
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Record start time
        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate duration in milliseconds
        duration_ms = round((time.time() - start_time) * 1000)

        # Log request details
        logger.info(
            f"Request: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration_ms}ms",
            extra={
                "http_request": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )

        return response
