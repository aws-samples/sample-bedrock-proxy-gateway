# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for observability.guardrail_metrics module."""

from unittest.mock import patch

from observability.guardrail_metrics import (
    record_guardrail_applied,
    record_guardrail_not_found,
)


class TestGuardrailMetrics:
    """Test cases for guardrail metrics functions."""

    @patch("observability.guardrail_metrics.guardrail_applied_total")
    def test_record_guardrail_applied(self, mock_counter):
        """Test recording guardrail applied metrics."""
        record_guardrail_applied("client-123", "baseline-security", "account-456", "converse")

        mock_counter.add.assert_called_once_with(
            1,
            {
                "client_id": "client-123",
                "logical_id": "baseline-security",
                "account_id": "account-456",
                "api_type": "converse",
            },
        )

    @patch("observability.guardrail_metrics.guardrail_not_found_total")
    def test_record_guardrail_not_found(self, mock_counter):
        """Test recording guardrail not found metrics."""
        record_guardrail_not_found("client-123", "nonexistent", "account-456")

        mock_counter.add.assert_called_once_with(
            1,
            {
                "client_id": "client-123",
                "logical_id": "nonexistent",
                "account_id": "account-456",
            },
        )

    @patch("observability.guardrail_metrics.guardrail_applied_total")
    def test_record_guardrail_applied_invoke(self, mock_counter):
        """Test recording guardrail applied for invoke API."""
        record_guardrail_applied("client-123", "baseline-security", "account-456", "invoke")

        mock_counter.add.assert_called_once_with(
            1,
            {
                "client_id": "client-123",
                "logical_id": "baseline-security",
                "account_id": "account-456",
                "api_type": "invoke",
            },
        )

    @patch("observability.guardrail_metrics.guardrail_applied_total")
    def test_record_guardrail_applied_apply(self, mock_counter):
        """Test recording guardrail applied for apply API."""
        record_guardrail_applied("unknown", "baseline-security", "account-456", "apply")

        mock_counter.add.assert_called_once_with(
            1,
            {
                "client_id": "unknown",
                "logical_id": "baseline-security",
                "account_id": "account-456",
                "api_type": "apply",
            },
        )
