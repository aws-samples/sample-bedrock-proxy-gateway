# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.rate_limit.stream_reconciler module."""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.rate_limit.eventstream_parser import (
    EventStreamMessage,
    EventStreamParser,
    Header,
    HeaderType,
)
from core.rate_limit.stream_reconciler import (
    ReconciliationContext,
    StreamOutcome,
    StreamTokenReconciler,
    TerminalUsage,
)
from core.rate_limit.tokens import TokenCounter
from util.constants import RATELIMIT_UNLIMITED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    *,
    rate_ctx_present: bool = True,
    tpm_limit: int = 1000,
    estimated_tokens: int = 50,
    endpoint: str = "converse-stream",
    model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0",
    client_id: str = "test-client",
    account_id: str = "123456789",
    api_type: str = "converse-stream",
) -> ReconciliationContext:
    """Create a ReconciliationContext for tests."""
    return ReconciliationContext(
        client_id=client_id,
        model_id=model_id,
        account_id=account_id,
        tpm_limit=tpm_limit,
        api_type=api_type,
        endpoint=endpoint,
        estimated_tokens=estimated_tokens,
        rate_ctx_present=rate_ctx_present,
    )


def _make_metadata_chunk(
    input_tokens: int = 100, output_tokens: int = 200, cache_write: int = 0
) -> bytes:
    """Build an encoded EventStream metadata message with usage data."""
    parser = EventStreamParser()
    payload = json.dumps(
        {
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "cacheWriteInputTokens": cache_write,
            }
        }
    ).encode()
    msg = EventStreamMessage(
        headers=(
            Header(name=":event-type", wire_type=HeaderType.STRING, value="metadata"),
        ),
        payload=payload,
    )
    return parser.encode(msg)


def _make_invoke_metrics_chunk(
    input_tokens: int = 100, output_tokens: int = 200, cache_write: int = 0
) -> bytes:
    """Build an encoded EventStream chunk message with invocationMetrics."""
    parser = EventStreamParser()
    payload = json.dumps(
        {
            "amazon-bedrock-invocationMetrics": {
                "inputTokenCount": input_tokens,
                "outputTokenCount": output_tokens,
                "cacheWriteInputTokenCount": cache_write,
            }
        }
    ).encode()
    msg = EventStreamMessage(
        headers=(
            Header(name=":event-type", wire_type=HeaderType.STRING, value="chunk"),
        ),
        payload=payload,
    )
    return parser.encode(msg)


async def _collect(reconciler: StreamTokenReconciler) -> list[bytes]:
    """Collect all chunks from the reconciler async iterator."""
    result = []
    async for chunk in reconciler:
        result.append(chunk)
    return result


async def _make_upstream(chunks: list[bytes]):
    """Create an async iterator from a list of byte chunks."""
    for chunk in chunks:
        yield chunk


async def _make_error_upstream(chunks: list[bytes], error: Exception):
    """Yield chunks then raise an error."""
    for chunk in chunks:
        yield chunk
    raise error


# ---------------------------------------------------------------------------
# Feature: streaming-tpm-reconciliation, Property 4: Streaming pipeline fidelity
# ---------------------------------------------------------------------------


class TestStreamReconcilerFidelity:
    """Property test: reconciler forwards bytes unchanged."""

    @settings(max_examples=200, deadline=timedelta(milliseconds=500))
    @given(
        chunks=st.lists(
            st.binary(min_size=0, max_size=8192),
            min_size=0,
            max_size=100,
        )
    )
    async def test_property_yields_input_byte_for_byte(self, chunks):
        """Property: yielded == input byte-for-byte and element-for-element."""
        ctx = _make_ctx(rate_ctx_present=False)
        tokens = TokenCounter()
        limiter = AsyncMock()

        upstream = _make_upstream(chunks)
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)

        collected = await _collect(reconciler)
        assert collected == chunks


# ---------------------------------------------------------------------------
# Example tests: StreamOutcome matrix
# ---------------------------------------------------------------------------


class TestStreamOutcomeMatrix:
    """Example tests for each StreamOutcome branch."""

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    async def test_completed_with_valid_metadata(self, mock_delta, mock_consumed):
        """Completed stream with valid metadata -> check_and_consume called with delta."""
        metadata_bytes = _make_metadata_chunk(input_tokens=100, output_tokens=200, cache_write=10)
        ctx = _make_ctx(estimated_tokens=50, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        upstream = _make_upstream([b"hello", metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        collected = await _collect(reconciler)

        assert collected == [b"hello", metadata_bytes]
        limiter.check_and_consume.assert_called_once()
        call_args = limiter.check_and_consume.call_args
        # Key format: {client_id:model_id}:client:tpm
        assert "test-client" in call_args[0][0]
        mock_delta.assert_called_once()
        mock_consumed.assert_called_once()

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    async def test_upstream_error_no_write(self, mock_delta, mock_consumed):
        """Upstream error -> no check_and_consume, skipped with reason."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        async def _error_upstream():
            yield b"partial"
            raise RuntimeError("upstream broke")

        reconciler = StreamTokenReconciler(_error_upstream(), ctx, tokens, limiter)

        with pytest.raises(RuntimeError, match="upstream broke"):
            await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_delta.assert_not_called()

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    async def test_client_disconnect_no_write_reraises(self, mock_delta, mock_consumed):
        """CancelledError -> no write, re-raised."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        async def _cancel_upstream():
            yield b"data"
            raise asyncio.CancelledError()

        reconciler = StreamTokenReconciler(_cancel_upstream(), ctx, tokens, limiter)

        with pytest.raises(asyncio.CancelledError):
            await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_delta.assert_not_called()

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    async def test_missing_usage_no_write(self, mock_delta, mock_consumed):
        """No metadata event in stream -> no write, skipped."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        # Just plain data, no terminal usage event
        upstream = _make_upstream([b"chunk1", b"chunk2"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        collected = await _collect(reconciler)

        assert collected == [b"chunk1", b"chunk2"]
        limiter.check_and_consume.assert_not_called()
        mock_delta.assert_not_called()
        mock_consumed.assert_not_called()


# ---------------------------------------------------------------------------
# Example tests: Exception isolation
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    """Tests that internal failures don't affect byte forwarding."""

    async def test_parser_raises_mid_stream_bytes_still_forwarded(self):
        """Parser raises mid-stream -> bytes still forwarded correctly."""
        ctx = _make_ctx(rate_ctx_present=False)
        tokens = TokenCounter()
        limiter = AsyncMock()
        parser = MagicMock(spec=EventStreamParser)
        parser.decode_all.side_effect = RuntimeError("parser exploded")
        parser.is_converse_metadata.return_value = False
        parser.is_invoke_metrics_chunk.return_value = False

        upstream = _make_upstream([b"chunk1", b"chunk2", b"chunk3"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter, parser=parser)
        collected = await _collect(reconciler)

        assert collected == [b"chunk1", b"chunk2", b"chunk3"]

    @patch("core.rate_limit.stream_reconciler.record_redis_failure")
    async def test_limiter_raises_record_redis_failure_called(self, mock_redis_failure):
        """Limiter raises -> record_redis_failure called, no re-raise."""
        metadata_bytes = _make_metadata_chunk(input_tokens=50, output_tokens=100)
        ctx = _make_ctx(estimated_tokens=30, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(side_effect=ConnectionError("redis down"))

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        collected = await _collect(reconciler)

        # Bytes still forwarded
        assert collected == [metadata_bytes]
        mock_redis_failure.assert_called_once_with(
            "stream_reconciliation", "ConnectionError"
        )

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_logger_raises_reconciler_completes(self, mock_logger):
        """Logger raises -> reconciler completes normally."""
        metadata_bytes = _make_metadata_chunk(input_tokens=50, output_tokens=100)
        ctx = _make_ctx(estimated_tokens=30, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        # Make info calls raise
        mock_logger.info.side_effect = RuntimeError("logging broken")
        mock_logger.error.side_effect = RuntimeError("logging broken")

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        collected = await _collect(reconciler)

        # Should still complete without error
        assert collected == [metadata_bytes]


# ---------------------------------------------------------------------------
# Example tests: Skip reasons
# ---------------------------------------------------------------------------


class TestSkipReasons:
    """Tests for each skip reason path."""

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_rate_ctx_absent(self, mock_logger):
        """rate_ctx_absent -> skipped log and zero check_and_consume calls."""
        ctx = _make_ctx(rate_ctx_present=False)
        tokens = TokenCounter()
        limiter = AsyncMock()

        upstream = _make_upstream([b"data"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_logger.info.assert_called()
        # Check that reason is in the log call
        call_args = mock_logger.info.call_args
        assert call_args[1]["extra"]["reason"] == "rate_ctx_absent"

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_tpm_limit_unlimited(self, mock_logger):
        """tpm_limit_unlimited -> skipped log and zero check_and_consume calls."""
        ctx = _make_ctx(tpm_limit=RATELIMIT_UNLIMITED)
        tokens = TokenCounter()
        limiter = AsyncMock()

        upstream = _make_upstream([b"data"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        assert call_args[1]["extra"]["reason"] == "tpm_limit_unlimited"

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_upstream_error_skip(self, mock_logger):
        """upstream_error -> skipped log and zero check_and_consume calls."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        async def _error():
            yield b"x"
            raise ValueError("boom")

        reconciler = StreamTokenReconciler(_error(), ctx, tokens, limiter)
        with pytest.raises(ValueError):
            await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        assert call_args[1]["extra"]["reason"] == "upstream_error"

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_client_disconnect_skip(self, mock_logger):
        """client_disconnect -> skipped log and zero check_and_consume calls."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        async def _cancel():
            yield b"x"
            raise asyncio.CancelledError()

        reconciler = StreamTokenReconciler(_cancel(), ctx, tokens, limiter)
        with pytest.raises(asyncio.CancelledError):
            await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        assert call_args[1]["extra"]["reason"] == "client_disconnect"

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_missing_usage_skip(self, mock_logger):
        """missing_usage -> skipped log and zero check_and_consume calls."""
        ctx = _make_ctx(tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()

        upstream = _make_upstream([b"no metadata here"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()
        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args
        assert call_args[1]["extra"]["reason"] == "missing_usage"

    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_unknown_endpoint_skip(self, mock_logger):
        """Unknown endpoint -> missing_usage (no terminal extraction)."""
        ctx = _make_ctx(tpm_limit=5000, endpoint="unknown-endpoint")
        tokens = TokenCounter()
        limiter = AsyncMock()

        upstream = _make_upstream([b"data"])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        limiter.check_and_consume.assert_not_called()


# ---------------------------------------------------------------------------
# Example tests: Log / metric shape
# ---------------------------------------------------------------------------


class TestLogMetricShape:
    """Tests for correct log event and metric emission."""

    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_successful_reconciliation_log_fields(
        self, mock_logger, mock_consumed, mock_delta
    ):
        """Successful reconciliation -> stream_reconciliation_applied log with all fields."""
        metadata_bytes = _make_metadata_chunk(input_tokens=100, output_tokens=200, cache_write=10)
        ctx = _make_ctx(estimated_tokens=50, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        # Find the applied log call
        info_calls = mock_logger.info.call_args_list
        applied_call = None
        for call in info_calls:
            if call[1].get("extra", {}).get("event.name") == "stream_reconciliation_applied":
                applied_call = call
                break

        assert applied_call is not None
        extra = applied_call[1]["extra"]
        assert "gen_ai.request.model" in extra
        assert "client.id" in extra
        assert "gen_ai.usage.input_tokens" in extra
        assert "gen_ai.usage.output_tokens" in extra
        assert "rate_limit.estimated_tokens" in extra
        assert "rate_limit.aggregated_tokens" in extra
        assert "rate_limit.reconciliation_delta" in extra

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    async def test_record_tokens_consumed_called_with_aggregated(
        self, mock_delta, mock_consumed
    ):
        """record_tokens_consumed called with aggregated_tokens."""
        metadata_bytes = _make_metadata_chunk(input_tokens=100, output_tokens=200, cache_write=10)
        ctx = _make_ctx(estimated_tokens=50, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        # Verify record_tokens_consumed was called
        mock_consumed.assert_called_once()
        call_args = mock_consumed.call_args[0]
        assert call_args[0] == "test-client"  # client_id
        # aggregated tokens should be calculated
        expected_aggregated = tokens.calculate_aggregated_tokens(
            {"inputTokens": 100, "outputTokens": 200, "cacheWriteInputTokens": 10},
            ctx.model_id,
        )
        assert call_args[2] == expected_aggregated

    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    async def test_record_stream_reconciliation_delta_recorded(
        self, mock_consumed, mock_delta
    ):
        """record_stream_reconciliation_delta recorded with delta."""
        metadata_bytes = _make_metadata_chunk(input_tokens=100, output_tokens=200, cache_write=10)
        estimated = 50
        ctx = _make_ctx(estimated_tokens=estimated, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)
        await _collect(reconciler)

        mock_delta.assert_called_once()
        call_args = mock_delta.call_args[0]
        expected_aggregated = tokens.calculate_aggregated_tokens(
            {"inputTokens": 100, "outputTokens": 200, "cacheWriteInputTokens": 10},
            ctx.model_id,
        )
        expected_delta = expected_aggregated - estimated
        assert call_args[3] == expected_delta

    @patch("core.rate_limit.stream_reconciler.record_tokens_consumed")
    @patch("core.rate_limit.stream_reconciler.record_stream_reconciliation_delta")
    @patch("core.rate_limit.stream_reconciler.logger")
    async def test_missing_field_suppressed_error_log(
        self, mock_logger, mock_delta, mock_consumed
    ):
        """Missing required field -> suppressed, error log emitted."""
        metadata_bytes = _make_metadata_chunk(input_tokens=100, output_tokens=200, cache_write=10)
        ctx = _make_ctx(estimated_tokens=50, tpm_limit=5000)
        tokens = TokenCounter()
        limiter = AsyncMock()
        limiter.check_and_consume = AsyncMock(return_value=(True, 0))

        upstream = _make_upstream([metadata_bytes])
        reconciler = StreamTokenReconciler(upstream, ctx, tokens, limiter)

        # Patch _missing_applied_fields to return a missing field
        reconciler._missing_applied_fields = lambda *args: ["gen_ai.request.model"]

        await _collect(reconciler)

        # Should have error log about suppressed
        error_calls = mock_logger.error.call_args_list
        suppressed_call = None
        for call in error_calls:
            if "suppressed" in str(call[0][0]).lower():
                suppressed_call = call
                break

        assert suppressed_call is not None
        # When applied_emitted is False, metrics are not recorded
        mock_delta.assert_not_called()
        mock_consumed.assert_not_called()
        # But check_and_consume is still called (delta application is independent of log emission)
        limiter.check_and_consume.assert_called_once()
