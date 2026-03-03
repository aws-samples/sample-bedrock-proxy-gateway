"""Unit tests for util.aws_error_response module."""

import json

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from util.aws_error_response import (
    create_aws_error_json,
    create_aws_error_response,
    create_aws_http_exception,
)


class TestAwsErrorResponse:
    """Test cases for AWS error response utilities."""

    def test_create_aws_error_response_basic(self):
        """Test basic AWS error response creation."""
        response = create_aws_error_response(
            status_code=400,
            error_code="ValidationException",
            error_message="Invalid parameter",
            request_id="test-request-id",
        )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        content = json.loads(response.body.decode())
        # Dual format: top-level for boto3, nested for other SDKs
        assert content["message"] == "Invalid parameter"
        assert content["__type"] == "ValidationException"
        assert content["Error"]["Code"] == "ValidationException"
        assert content["Error"]["Message"] == "Invalid parameter"
        assert content["RequestId"] == "test-request-id"

        assert response.headers["content-type"] == "application/x-amz-json-1.1"
        assert response.headers["x-amzn-errortype"] == "ValidationException"
        assert response.headers["x-amzn-requestid"] == "test-request-id"

    def test_create_aws_error_response_with_additional_headers(self):
        """Test AWS error response with additional headers."""
        response = create_aws_error_response(
            status_code=403,
            error_code="AccessDenied",
            error_message="Access denied",
            request_id="test-id",
            headers={"X-Custom-Header": "custom-value"},
        )

        assert response.headers["x-custom-header"] == "custom-value"
        assert response.headers["x-amzn-errortype"] == "AccessDenied"

    def test_create_aws_http_exception_basic(self):
        """Test basic AWS HTTPException creation."""
        exception = create_aws_http_exception(
            status_code=400,
            error_code="ValidationException",
            error_message="Guardrail is not supported with the chosen model",
            request_id="invoke-bedrock-error",
        )

        assert isinstance(exception, HTTPException)
        assert exception.status_code == 400
        # Dual format: top-level for boto3, nested for other SDKs
        assert exception.detail["message"] == "Guardrail is not supported with the chosen model"
        assert exception.detail["__type"] == "ValidationException"
        assert exception.detail["Error"]["Code"] == "ValidationException"
        assert (
            exception.detail["Error"]["Message"]
            == "Guardrail is not supported with the chosen model"
        )
        assert exception.detail["RequestId"] == "invoke-bedrock-error"

        assert exception.headers["Content-Type"] == "application/x-amz-json-1.1"
        assert exception.headers["x-amzn-ErrorType"] == "ValidationException"
        assert exception.headers["x-amzn-RequestId"] == "invoke-bedrock-error"

    def test_create_aws_error_json_basic(self):
        """Test AWS error JSON creation for streaming."""
        error_json = create_aws_error_json(
            error_code="ThrottlingException",
            error_message="Rate limit exceeded",
            request_id="stream-error-id",
        )

        assert isinstance(error_json, bytes)
        data = json.loads(error_json.decode().strip())
        # Dual format: top-level for boto3, nested for other SDKs
        assert data["message"] == "Rate limit exceeded"
        assert data["__type"] == "ThrottlingException"
        assert data["Error"]["Code"] == "ThrottlingException"
        assert data["Error"]["Message"] == "Rate limit exceeded"
        assert data["RequestId"] == "stream-error-id"

    def test_create_aws_error_response_default_request_id(self):
        """Test AWS error response with default request ID."""
        response = create_aws_error_response(
            status_code=500, error_code="InternalServerError", error_message="Internal error"
        )

        content = json.loads(response.body.decode())
        assert content["RequestId"] == "gateway-error"
        assert response.headers["x-amzn-requestid"] == "gateway-error"

    def test_create_aws_http_exception_default_request_id(self):
        """Test AWS HTTPException with default request ID."""
        exception = create_aws_http_exception(
            status_code=500, error_code="InternalServerError", error_message="Internal error"
        )

        assert exception.detail["RequestId"] == "gateway-error"
        assert exception.headers["x-amzn-RequestId"] == "gateway-error"

    def test_create_aws_error_json_default_request_id(self):
        """Test AWS error JSON with default request ID."""
        error_json = create_aws_error_json(
            error_code="InternalServerError", error_message="Internal error"
        )

        data = json.loads(error_json.decode().strip())
        assert data["message"] == "Internal error"
        assert data["__type"] == "InternalServerError"
        assert data["RequestId"] == "stream-error"
