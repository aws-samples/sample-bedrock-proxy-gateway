"""Unit tests for observability.guardrail_tracing module."""

from unittest.mock import ANY, Mock, patch

import pytest
from observability.guardrail_tracing import guardrail_span


class TestGuardrailTracing:
    """Test cases for guardrail tracing utilities."""

    @pytest.mark.asyncio
    @patch("observability.guardrail_tracing.tracer")
    async def test_guardrail_span_success(self, mock_tracer):
        """Test successful guardrail span creation."""
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)

        async with guardrail_span() as span:
            assert span == mock_span

        mock_tracer.start_as_current_span.assert_called_once_with("guardrail_middleware")
        mock_span.set_status.assert_called_once_with(ANY)

    @pytest.mark.asyncio
    @patch("observability.guardrail_tracing.tracer")
    async def test_guardrail_span_exception(self, mock_tracer):
        """Test guardrail span with exception handling."""
        mock_span = Mock()
        mock_tracer.start_as_current_span.return_value.__enter__ = Mock(return_value=mock_span)
        mock_tracer.start_as_current_span.return_value.__exit__ = Mock(return_value=None)

        test_exception = Exception("Test error")

        with pytest.raises(Exception) as exc_info:
            async with guardrail_span():
                raise test_exception

        assert exc_info.value == test_exception
        mock_tracer.start_as_current_span.assert_called_once_with("guardrail_middleware")
        mock_span.set_status.assert_called_once_with(ANY)
        mock_span.record_exception.assert_called_once_with(test_exception)
