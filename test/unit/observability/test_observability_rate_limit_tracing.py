"""Unit tests for observability.rate_limit_tracing module."""

from unittest.mock import Mock, patch

import pytest
from observability.rate_limit_tracing import rate_limit_span
from opentelemetry.trace import StatusCode


class TestRateLimitTracing:
    """Test cases for rate limit tracing functions."""

    @pytest.mark.asyncio
    @patch("observability.rate_limit_tracing.tracer")
    async def test_rate_limit_span_success(self, mock_tracer):
        """Test successful rate limit span creation."""
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)

        async with rate_limit_span() as span:
            assert span == mock_span

        mock_tracer.start_as_current_span.assert_called_once_with("rate_limit_middleware")
        mock_span.set_status.assert_called_once()
        status_call = mock_span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.OK

    @pytest.mark.asyncio
    @patch("observability.rate_limit_tracing.tracer")
    async def test_rate_limit_span_with_exception(self, mock_tracer):
        """Test rate limit span with exception handling."""
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)

        test_error = ValueError("Test error")

        with pytest.raises(ValueError):
            async with rate_limit_span():
                raise test_error

        mock_span.set_status.assert_called_once()
        status_call = mock_span.set_status.call_args[0][0]
        assert status_call.status_code == StatusCode.ERROR
        assert status_call.description == "Test error"
        mock_span.record_exception.assert_called_once_with(test_error)

    @pytest.mark.asyncio
    @patch("observability.rate_limit_tracing.tracer")
    async def test_rate_limit_span_context_manager(self, mock_tracer):
        """Test rate limit span as context manager."""
        mock_span = Mock()
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=mock_span)
        mock_context.__exit__ = Mock(return_value=None)
        mock_tracer.start_as_current_span.return_value = mock_context

        async with rate_limit_span():
            pass

        mock_tracer.start_as_current_span.assert_called_once_with("rate_limit_middleware")
        mock_context.__enter__.assert_called_once()
        mock_context.__exit__.assert_called_once()
