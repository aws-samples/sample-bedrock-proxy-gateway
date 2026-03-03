"""Unit tests for middleware.logging module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import Request
from middleware.logging import LoggingMiddleware


class TestLoggingMiddleware:
    """Test cases for LoggingMiddleware class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = Mock()
        self.middleware = LoggingMiddleware(self.app)

    @pytest.mark.asyncio
    async def test_dispatch_public_path(self):
        """Test middleware bypass for public paths."""
        request = Mock(spec=Request)
        request.url.path = "/health"

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        result = await self.middleware.dispatch(request, call_next)

        assert result == expected_response
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch("middleware.logging.time")
    @patch("middleware.logging.logger")
    async def test_dispatch_logs_request_duration(self, mock_logger, mock_time):
        """Test middleware logs request duration for non-public paths."""
        # Setup request mock
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.method = "POST"

        # Setup response mock
        response = Mock()
        response.status_code = 200

        # Setup time mock to simulate elapsed time
        mock_time.time.side_effect = [100.0, 100.5]  # Start time, end time (500ms difference)

        # Setup call_next mock
        call_next = AsyncMock(return_value=response)

        # Call the middleware
        result = await self.middleware.dispatch(request, call_next)

        # Verify the response is passed through
        assert result == response
        call_next.assert_called_once_with(request)

        # Verify logging
        mock_logger.info.assert_called_once_with(
            "Request: POST /model/test/converse - Status: 200 - Duration: 500ms",
            extra={
                "http_request": {
                    "method": "POST",
                    "path": "/model/test/converse",
                    "status_code": 200,
                    "duration_ms": 500,
                }
            },
        )

    @pytest.mark.asyncio
    async def test_public_paths_coverage(self):
        """Test all public paths are handled correctly."""
        public_paths = ["/", "/docs", "/openapi.json", "/redoc", "/health", "/debug"]

        call_next = AsyncMock()
        expected_response = Mock()
        call_next.return_value = expected_response

        for path in public_paths:
            request = Mock(spec=Request)
            request.url.path = path

            result = await self.middleware.dispatch(request, call_next)

            assert result == expected_response
            call_next.assert_called_with(request)

    @pytest.mark.asyncio
    @patch("middleware.logging.time")
    @patch("middleware.logging.logger")
    async def test_dispatch_handles_exception_in_call_next(self, mock_logger, mock_time):
        """Test middleware correctly handles exceptions in call_next."""
        # Setup request mock
        request = Mock(spec=Request)
        request.url.path = "/model/test/converse"
        request.method = "POST"

        # Setup time mock
        mock_time.time.side_effect = [100.0, 100.3]  # Start time, end time (300ms difference)

        # Setup call_next to raise an exception
        exception = ValueError("Test exception")
        call_next = AsyncMock(side_effect=exception)

        # Call the middleware and expect the exception to be propagated
        with pytest.raises(ValueError) as excinfo:
            await self.middleware.dispatch(request, call_next)

        assert str(excinfo.value) == "Test exception"
        call_next.assert_called_once_with(request)

        # Verify no logging occurred since the exception was raised
        mock_logger.info.assert_not_called()
