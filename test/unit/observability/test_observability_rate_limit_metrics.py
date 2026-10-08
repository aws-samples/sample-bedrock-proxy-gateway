# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for observability.rate_limit_metrics module."""

from unittest.mock import patch

from observability.rate_limit_metrics import (
    record_rate_limit_exceeded,
    record_rate_limit_request,
    record_redis_failure,
    record_stream_reconciliation_delta,
    record_tokens_consumed,
)


class TestRateLimitMetrics:
    """Test cases for rate limit metrics functions."""

    @patch("observability.rate_limit_metrics.rate_limit_requests_total")
    def test_record_rate_limit_request(self, mock_counter):
        """Test record_rate_limit_request function."""
        record_rate_limit_request("client-123", "claude-3", "account-456", "allowed")

        mock_counter.add.assert_called_once_with(
            1,
            {
                "client_id": "client-123",
                "model_id": "claude-3",
                "account_id": "account-456",
                "result": "allowed",
            },
        )

    @patch("observability.rate_limit_metrics.rate_limit_exceeded_total")
    def test_record_rate_limit_exceeded(self, mock_counter):
        """Test record_rate_limit_exceeded function."""
        record_rate_limit_exceeded("client-123", "claude-3", "rpm")

        mock_counter.add.assert_called_once_with(
            1, {"client_id": "client-123", "model_id": "claude-3", "limit_type": "rpm"}
        )

    @patch("observability.rate_limit_metrics.redis_failures_total")
    def test_record_redis_failure(self, mock_counter):
        """Test record_redis_failure function."""
        record_redis_failure("quota_check", "ConnectionError")

        mock_counter.add.assert_called_once_with(
            1, {"operation": "quota_check", "error_type": "ConnectionError"}
        )

    @patch("observability.rate_limit_metrics.tokens_consumed_total")
    def test_record_tokens_consumed(self, mock_counter):
        """Test record_tokens_consumed function."""
        record_tokens_consumed("client-123", "claude-3", 250, "converse")

        mock_counter.add.assert_called_once_with(
            250, {"client_id": "client-123", "model_id": "claude-3", "api_type": "converse"}
        )

    @patch("observability.rate_limit_metrics.rate_limit_requests_total")
    def test_record_rate_limit_request_different_results(self, mock_counter):
        """Test record_rate_limit_request with different result types."""
        test_cases = [("exceeded", "none"), ("unlimited", "account-789"), ("error", "account-123")]

        for result, account_id in test_cases:
            record_rate_limit_request("client-456", "model-test", account_id, result)

        assert mock_counter.add.call_count == 3

    @patch("observability.rate_limit_metrics.rate_limit_exceeded_total")
    def test_record_rate_limit_exceeded_different_types(self, mock_counter):
        """Test record_rate_limit_exceeded with different limit types."""
        test_cases = ["rpm", "tpm", "rpm_or_tpm"]

        for limit_type in test_cases:
            record_rate_limit_exceeded("client-789", "model-test", limit_type)

        assert mock_counter.add.call_count == 3

    @patch("observability.rate_limit_metrics.redis_failures_total")
    def test_record_redis_failure_different_operations(self, mock_counter):
        """Test record_redis_failure with different operations and error types."""
        test_cases = [
            ("token_update", "Exception"),
            ("round_robin", "TimeoutError"),
            ("quota_check", "RedisError"),
        ]

        for operation, error_type in test_cases:
            record_redis_failure(operation, error_type)

        assert mock_counter.add.call_count == 3

    @patch("observability.rate_limit_metrics.tokens_consumed_total")
    def test_record_tokens_consumed_different_api_types(self, mock_counter):
        """Test record_tokens_consumed with different API types."""
        test_cases = [(100, "invoke"), (500, "converse-stream"), (1000, "converse")]

        for tokens, api_type in test_cases:
            record_tokens_consumed("client-test", "model-test", tokens, api_type)

        assert mock_counter.add.call_count == 3

    @patch("observability.rate_limit_metrics.stream_reconciliation_delta")
    def test_record_stream_reconciliation_delta(self, mock_histogram):
        """Test record_stream_reconciliation_delta histogram record."""
        record_stream_reconciliation_delta("client-abc", "claude-model", "converse-stream", 42)

        mock_histogram.record.assert_called_once_with(
            42,
            {
                "client_id": "client-abc",
                "model_id": "claude-model",
                "endpoint": "converse-stream",
            },
        )

    @patch("observability.rate_limit_metrics.stream_reconciliation_delta")
    def test_record_stream_reconciliation_delta_negative(self, mock_histogram):
        """Test record_stream_reconciliation_delta with negative delta."""
        record_stream_reconciliation_delta(
            "client-xyz", "model-test", "invoke-with-response-stream", -15
        )

        mock_histogram.record.assert_called_once_with(
            -15,
            {
                "client_id": "client-xyz",
                "model_id": "model-test",
                "endpoint": "invoke-with-response-stream",
            },
        )
