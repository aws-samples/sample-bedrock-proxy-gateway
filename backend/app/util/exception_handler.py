# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Global exception handler module for FastAPI applications."""

from fastapi import HTTPException, Request


def create_global_exception_handler(logger):
    """Create global exception handler with logger.

    Args:
    ----
        logger: Logger instance for error reporting.

    Returns:
    -------
        Callable: Exception handler function.
    """

    async def global_exception_handler(request: Request, exc: Exception):  # noqa: ARG001
        """Global exception handler to prevent API failures from affecting subsequent requests.

        Args:
        ----
            request: The incoming request object.
            exc: The exception that was raised.

        Returns:
        -------
            JSONResponse: Response containing error details with 500 status code.
        """
        # Handle HTTPExceptions by returning proper response
        if isinstance(exc, HTTPException):
            from util.aws_error_response import create_aws_error_response

            # Extract error details from structured detail dict if available
            if isinstance(exc.detail, dict):
                # Check for nested AWS error structure first
                if "Error" in exc.detail:
                    error_code = exc.detail["Error"].get("Code", "ClientError")
                    error_message = exc.detail["Error"].get("Message", "")
                    request_id = exc.detail.get("RequestId", "http-exception")
                # Check for top-level boto3 format
                elif "__type" in exc.detail:
                    error_code = exc.detail.get("__type", "ClientError")
                    error_message = exc.detail.get("message", "")
                    request_id = "http-exception"
                else:
                    # Dict but no recognized format
                    error_code = "ValidationException" if exc.status_code == 400 else "ClientError"
                    error_message = str(exc.detail)
                    request_id = "http-exception"
            else:
                # Fallback for non-dict detail
                error_code = "ValidationException" if exc.status_code == 400 else "ClientError"
                error_message = str(exc.detail)
                request_id = "http-exception"

            return create_aws_error_response(
                status_code=exc.status_code,
                error_code=error_code,
                error_message=error_message,
                request_id=request_id,
            )

        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

        from util.aws_error_response import create_aws_error_response

        return create_aws_error_response(
            status_code=500,
            error_code="InternalServerError",
            error_message="Internal server error",
            request_id="global-exception-handler",
        )

    return global_exception_handler
