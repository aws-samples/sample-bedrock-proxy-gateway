# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""AWS SDK compatible error response utilities."""

import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def _create_aws_error_data(error_code: str, error_message: str, request_id: str) -> dict:
    """Create AWS SDK compatible error data structure.

    Uses dual format for compatibility:
    - Top-level 'message' for boto3 rest-json parser
    - Nested 'Error' object for other AWS SDKs (Java, C#, etc.)

    Args:
    ----
        error_code: AWS error code (e.g., AccessDenied, ValidationException)
        error_message: Human readable error message
        request_id: Request identifier for tracking

    Returns:
    -------
        Dictionary with multi-SDK compatible error format
    """
    return {
        "message": error_message,
        "__type": error_code,
        "Error": {"Code": error_code, "Message": error_message},
        "RequestId": request_id,
    }


def _get_aws_headers(
    error_code: str | None = None,
    request_id: str | None = None,
    additional_headers: dict | None = None,
) -> dict:
    """Get AWS SDK compatible headers.

    Args:
    ----
        error_code: AWS error code for x-amzn-ErrorType header
        request_id: Request ID for x-amzn-RequestId header
        additional_headers: Additional headers to include

    Returns:
    -------
        Dictionary with AWS SDK compatible headers
    """
    headers = {"Content-Type": "application/x-amz-json-1.1"}
    if error_code:
        headers["x-amzn-ErrorType"] = error_code
    if request_id:
        headers["x-amzn-RequestId"] = request_id
    if additional_headers:
        headers.update(additional_headers)
    return headers


def create_aws_error_response(
    status_code: int,
    error_code: str,
    error_message: str,
    request_id: str = "gateway-error",
    headers: dict | None = None,
) -> JSONResponse:
    """Create AWS SDK compatible error response.

    Args:
    ----
        status_code: HTTP status code
        error_code: AWS error code (e.g., AccessDenied, ValidationException)
        error_message: Human readable error message
        request_id: Request identifier for tracking
        headers: Additional headers to include

    Returns:
    -------
        JSONResponse with AWS SDK compatible error format
    """
    return JSONResponse(
        status_code=status_code,
        content=_create_aws_error_data(error_code, error_message, request_id),
        headers=_get_aws_headers(error_code, request_id, headers),
    )


def create_aws_http_exception(
    status_code: int, error_code: str, error_message: str, request_id: str = "gateway-error"
) -> HTTPException:
    """Create AWS SDK compatible HTTPException.

    Args:
    ----
        status_code: HTTP status code
        error_code: AWS error code (e.g., AccessDenied, ValidationException)
        error_message: Human readable error message
        request_id: Request identifier for tracking

    Returns:
    -------
        HTTPException with AWS SDK compatible error format
    """
    return HTTPException(
        status_code=status_code,
        detail=_create_aws_error_data(error_code, error_message, request_id),
        headers=_get_aws_headers(error_code, request_id),
    )


def create_aws_error_json(
    error_code: str, error_message: str, request_id: str = "stream-error"
) -> bytes:
    """Create AWS SDK compatible error JSON for streaming responses.

    Args:
    ----
        error_code: AWS error code (e.g., AccessDenied, ValidationException)
        error_message: Human readable error message
        request_id: Request identifier for tracking

    Returns:
    -------
        JSON bytes with AWS SDK compatible error format
    """
    error_data = _create_aws_error_data(error_code, error_message, request_id)
    return json.dumps(error_data).encode() + b"\n"
