# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for util.exception_handler module."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from util.exception_handler import create_global_exception_handler


class TestGlobalExceptionHandler:
    """Test cases for global exception handler."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_logger = Mock()
        self.handler = create_global_exception_handler(self.mock_logger)

    @pytest.mark.asyncio
    async def test_global_exception_handler_basic(self):
        """Test basic exception handling."""
        request = Mock(spec=Request)
        exception = Exception("Test error")

        response = await self.handler(request, exception)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500

        # Parse response content
        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "InternalServerError"
        assert content["Error"]["Message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_logs_error(self):
        """Test that exception handler logs the error."""
        request = Mock(spec=Request)
        exception = ValueError("Validation error")

        await self.handler(request, exception)

        self.mock_logger.error.assert_called_once()
        call_args = self.mock_logger.error.call_args
        assert "Unhandled exception: Validation error" in call_args[0][0]
        assert call_args[1]["exc_info"] is True

    @pytest.mark.asyncio
    async def test_global_exception_handler_different_exceptions(self):
        """Test handler with different exception types."""
        request = Mock(spec=Request)

        exceptions = [
            ValueError("Value error"),
            TypeError("Type error"),
            RuntimeError("Runtime error"),
            KeyError("Key error"),
        ]

        for exc in exceptions:
            response = await self.handler(request, exc)

            assert isinstance(response, JSONResponse)
            assert response.status_code == 500

            import json

            content = json.loads(response.body.decode())
            assert content["Error"]["Code"] == "InternalServerError"
            assert content["Error"]["Message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_response_format(self):
        """Test exception handler response format."""
        request = Mock(spec=Request)
        exception = Exception("Format test")

        response = await self.handler(request, exception)

        # Verify response structure
        import json

        content = json.loads(response.body.decode())

        assert "Error" in content
        assert "RequestId" in content
        assert content["Error"]["Code"] == "InternalServerError"
        assert content["Error"]["Message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_with_complex_exception(self):
        """Test handler with exception containing complex message."""
        request = Mock(spec=Request)
        exception = Exception("Complex error with special chars: !@#$%^&*()")

        response = await self.handler(request, exception)

        assert response.status_code == 500
        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "InternalServerError"
        assert content["Error"]["Message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_preserves_request(self):
        """Test that handler receives request object correctly."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/test/path"
        exception = Exception("Test error")

        # The handler should not modify the request
        original_request = request

        await self.handler(request, exception)

        assert request is original_request

    def test_create_global_exception_handler_returns_callable(self):
        """Test that create_global_exception_handler returns a callable."""
        logger = Mock()
        handler = create_global_exception_handler(logger)

        assert callable(handler)

    @pytest.mark.asyncio
    async def test_global_exception_handler_empty_exception_message(self):
        """Test handler with exception having empty message."""
        request = Mock(spec=Request)
        exception = Exception("")

        response = await self.handler(request, exception)

        assert response.status_code == 500
        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "InternalServerError"
        assert content["Error"]["Message"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_http_exception_400(self):
        """Test handling of HTTPException with 400 status code and string detail."""
        request = Mock(spec=Request)
        exception = HTTPException(status_code=400, detail="Bad request")

        response = await self.handler(request, exception)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "ValidationException"
        assert content["Error"]["Message"] == "Bad request"
        assert "RequestId" in content

    @pytest.mark.asyncio
    async def test_global_exception_handler_http_exception_404(self):
        """Test handling of HTTPException with 404 status code and string detail."""
        request = Mock(spec=Request)
        exception = HTTPException(status_code=404, detail="Not found")

        response = await self.handler(request, exception)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404

        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "ClientError"
        assert content["Error"]["Message"] == "Not found"
        assert "RequestId" in content

    @pytest.mark.asyncio
    async def test_global_exception_handler_http_exception_aws_error_structure(self):
        """Test handling of HTTPException with AWS error structure in detail dict.

        LOGIC: When route handlers catch ClientError from boto3, they create HTTPException
        with detail as a dict containing AWS error structure. The exception handler must
        extract error details from this dict to preserve AWS error codes and messages.

        EXPECTED: Error code, message, and request ID are extracted from detail dict.
        """
        request = Mock(spec=Request)
        aws_error_detail = {
            "Error": {
                "Code": "ValidationException",
                "Message": "Guardrail is not supported with the chosen model",
            },
            "RequestId": "bedrock-client-error",
        }
        exception = HTTPException(status_code=400, detail=aws_error_detail)

        response = await self.handler(request, exception)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "ValidationException"
        assert content["Error"]["Message"] == "Guardrail is not supported with the chosen model"
        assert content["RequestId"] == "bedrock-client-error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_http_exception_aws_error_403(self):
        """Test handling of HTTPException with AWS 403 error structure.

        LOGIC: Access denied errors from Bedrock should preserve the exact error code
        and message returned by AWS.

        EXPECTED: AccessDeniedException code and message are preserved.
        """
        request = Mock(spec=Request)
        aws_error_detail = {
            "Error": {
                "Code": "AccessDeniedException",
                "Message": "Access denied for model 'amazon.titan-embed-text-v1'. Model may not be enabled in your account or region.",
            },
            "RequestId": "invoke-bedrock-error",
        }
        exception = HTTPException(status_code=403, detail=aws_error_detail)

        response = await self.handler(request, exception)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 403

        import json

        content = json.loads(response.body.decode())
        assert content["Error"]["Code"] == "AccessDeniedException"
        assert "Access denied for model" in content["Error"]["Message"]
        assert content["RequestId"] == "invoke-bedrock-error"

    @pytest.mark.asyncio
    async def test_global_exception_handler_http_exception_no_logging(self):
        """Test that HTTPException does not trigger error logging."""
        request = Mock(spec=Request)
        exception = HTTPException(status_code=400, detail="Bad request")

        await self.handler(request, exception)

        # HTTPException should not be logged as an error
        self.mock_logger.error.assert_not_called()
