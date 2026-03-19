# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for observability.metrics module."""

import time
from unittest.mock import Mock, patch

import pytest
from observability.metrics import MetricsCollector


class TestMetricsCollector:
    """Test cases for MetricsCollector class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_meter = Mock()
        self.mock_tracer = Mock()
        self.mock_logger = Mock()

        # Set up mock metrics
        self.mock_auth_failures = Mock()
        self.mock_model_usage = Mock()
        self.mock_ttft_histogram = Mock()
        self.mock_active_requests = Mock()

        self.mock_meter.create_counter.side_effect = [
            self.mock_auth_failures,
            self.mock_model_usage,
        ]
        self.mock_meter.create_histogram.return_value = self.mock_ttft_histogram
        self.mock_meter.create_up_down_counter.return_value = self.mock_active_requests

        self.collector = MetricsCollector(self.mock_meter, self.mock_tracer, self.mock_logger)

    def test_init_creates_metrics(self):
        """Test metrics collector initialization."""
        assert self.collector.tracer == self.mock_tracer
        assert self.collector.logger == self.mock_logger
        assert self.collector.auth_failures == self.mock_auth_failures
        assert self.collector.model_usage == self.mock_model_usage
        assert self.collector.ttft_histogram == self.mock_ttft_histogram

    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    def test_record_auth_failure(self, mock_client_name, mock_client_id):
        """Test recording authentication failure."""
        mock_client_id.get.return_value = "test-org"
        mock_client_name.get.return_value = "test-client"

        self.collector.record_auth_failure("invalid_token")

        self.mock_auth_failures.add.assert_called_once_with(
            1,
            {
                "reason": "invalid_token",
                "client.id": "test-org",
                "client.name": "test-client",
            },
        )

    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    def test_record_auth_failure_no_context(self, mock_client_name, mock_client_id):
        """Test recording authentication failure without user context."""
        mock_client_id.get.return_value = None
        mock_client_name.get.return_value = None

        self.collector.record_auth_failure("invalid_token")

        self.mock_auth_failures.add.assert_called_once_with(1, {"reason": "invalid_token"})

    @pytest.mark.asyncio
    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    async def test_track_request_success(self, mock_client_name, mock_client_id):
        """Test successful request tracking."""
        mock_client_id.get.return_value = "test-org"
        mock_client_name.get.return_value = "test-client"

        async with self.collector.track_request("converse", "claude-v2"):
            pass

        self.mock_model_usage.add.assert_called_once_with(
            1,
            {
                "model_id": "claude-v2",
                "endpoint": "converse",
                "client.id": "test-org",
                "client.name": "test-client",
            },
        )
        self.mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_track_request_without_model_id(self):
        """Test request tracking without model ID."""
        async with self.collector.track_request("health"):
            pass

        self.mock_model_usage.add.assert_not_called()
        self.mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_track_request_with_exception(self):
        """Test request tracking with exception."""
        with pytest.raises(ValueError):
            async with self.collector.track_request("converse", "claude-v2"):
                raise ValueError("Test error")

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    async def test_track_stream_request_success(self, mock_client_name, mock_client_id):
        """Test successful stream request tracking."""
        mock_client_id.get.return_value = "test-org"
        mock_client_name.get.return_value = "test-client"

        async with self.collector.track_stream_request("converse-stream", "claude-v2") as ctx:
            assert ctx is not None
            assert hasattr(ctx, "record_first_token")
            assert hasattr(ctx, "record_failure")

        self.mock_model_usage.add.assert_called_once_with(
            1,
            {
                "model_id": "claude-v2",
                "endpoint": "converse-stream",
                "client.id": "test-org",
                "client.name": "test-client",
            },
        )

    @pytest.mark.asyncio
    async def test_track_stream_request_with_exception(self):
        """Test stream request tracking with exception."""
        with pytest.raises(ValueError):
            async with self.collector.track_stream_request("converse-stream", "claude-v2"):
                raise ValueError("Stream error")

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    async def test_stream_context_record_first_token(self, mock_client_name, mock_client_id):
        """Test stream context first token recording."""
        mock_client_id.get.return_value = "test-org"
        mock_client_name.get.return_value = "test-client"

        async with self.collector.track_stream_request("converse-stream", "claude-v2") as ctx:
            # Simulate some processing time
            time.sleep(0.1)
            ctx.record_first_token()

        # Verify TTFT was recorded
        self.mock_ttft_histogram.record.assert_called_once()
        call_args = self.mock_ttft_histogram.record.call_args
        ttft_value = call_args[0][0]
        ttft_attributes = call_args[0][1]

        assert ttft_value > 0
        assert ttft_attributes == {
            "model_id": "claude-v2",
            "endpoint": "converse-stream",
            "client.id": "test-org",
            "client.name": "test-client",
        }

    @pytest.mark.asyncio
    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    async def test_stream_context_record_first_token_once(self, mock_client_name, mock_client_id):
        """Test stream context records TTFT only once."""
        mock_client_id.get.return_value = None
        mock_client_name.get.return_value = None

        async with self.collector.track_stream_request("converse-stream", "claude-v2") as ctx:
            ctx.record_first_token()
            ctx.record_first_token()  # Second call should be ignored

        # Should only be called once
        assert self.mock_ttft_histogram.record.call_count == 1

    @pytest.mark.asyncio
    async def test_stream_context_record_failure(self):
        """Test stream context failure recording."""
        test_error = Exception("Stream failed")

        async with self.collector.track_stream_request("converse-stream", "claude-v2") as ctx:
            ctx.record_failure(test_error)

        self.mock_logger.error.assert_called()
        error_call = [
            call for call in self.mock_logger.error.call_args_list if "Stream failed" in str(call)
        ]
        assert len(error_call) > 0

    def test_metrics_instruments_created(self):
        """Test that all required metrics instruments are created."""
        # Verify counter creation calls
        counter_calls = self.mock_meter.create_counter.call_args_list
        assert len(counter_calls) == 2

        # Check auth failures counter
        auth_call = counter_calls[0]
        assert auth_call[1]["name"] == "auth_failures_total"
        assert auth_call[1]["description"] == "Authentication failures"

        # Check model usage counter
        usage_call = counter_calls[1]
        assert usage_call[1]["name"] == "model_usage_total"
        assert usage_call[1]["description"] == "Model usage by endpoint"

        # Check histogram creation
        histogram_call = self.mock_meter.create_histogram.call_args
        assert histogram_call[1]["name"] == "streaming_ttft_seconds"
        assert histogram_call[1]["description"] == "Time to first token for streaming responses"

    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    def test_get_user_attributes_with_context(self, mock_client_name, mock_client_id):
        """Test _get_user_attributes with context values."""
        mock_client_id.get.return_value = "test-org"
        mock_client_name.get.return_value = "test-client"

        attributes = self.collector._get_user_attributes()

        assert attributes == {
            "client.id": "test-org",
            "client.name": "test-client",
        }

    @patch("observability.metrics.client_id_context")
    @patch("observability.metrics.client_name_context")
    def test_get_user_attributes_without_context(self, mock_client_name, mock_client_id):
        """Test _get_user_attributes without context values."""
        mock_client_id.get.return_value = None
        mock_client_name.get.return_value = None

        attributes = self.collector._get_user_attributes()

        assert attributes == {}
