# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Post-stream TPM reconciliation for streaming Bedrock endpoints.

Wraps the upstream byte iterator, forwards each chunk to the client before
parsing, extracts the terminal usage event, and applies a signed delta to the
Shared_TPM_Key. Reconciliation failures never surface to the client.
"""

import asyncio
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from enum import Enum

from observability.context_logger import ContextLogger
from observability.rate_limit_metrics import (
    record_redis_failure,
    record_stream_reconciliation_delta,
    record_tokens_consumed,
)
from util.constants import RATELIMIT_UNLIMITED

from .eventstream_parser import EventStreamMessage, EventStreamParser
from .limiter import RateLimiter
from .tokens import TokenCounter

logger = ContextLogger(logging.getLogger(__name__))

# Signed 32-bit upper bound for clamping token counts.
_INT32_MAX: int = 2**31 - 1

# ---------------------------------------------------------------------------
# Enumerations and data models
# ---------------------------------------------------------------------------


class StreamOutcome(str, Enum):
    """Terminal state of a streaming response."""

    COMPLETED = "completed"
    UPSTREAM_ERROR = "upstream_error"
    CLIENT_DISCONNECT = "client_disconnect"
    MISSING_USAGE = "missing_usage"
    UNKNOWN = "unknown"


def _clamp_int32(value: int) -> int:
    """Clamp *value* to [0, 2**31 - 1]."""
    if value < 0:
        return 0
    if value > _INT32_MAX:
        return _INT32_MAX
    return value


@dataclass(frozen=True)
class TerminalUsage:
    """Token counts extracted from the terminal event, clamped to [0, 2**31-1]."""

    input_tokens: int
    output_tokens: int
    cache_write_input_tokens: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_tokens", _clamp_int32(self.input_tokens))
        object.__setattr__(self, "output_tokens", _clamp_int32(self.output_tokens))
        object.__setattr__(
            self,
            "cache_write_input_tokens",
            _clamp_int32(self.cache_write_input_tokens),
        )


@dataclass(frozen=True)
class ReconciliationContext:
    """Immutable snapshot of reconciliation inputs captured at install time."""

    client_id: str
    model_id: str
    account_id: str
    tpm_limit: int
    api_type: str
    endpoint: str
    estimated_tokens: int
    rate_ctx_present: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONVERSE_STREAM_ENDPOINT = "converse-stream"
_INVOKE_STREAM_ENDPOINT = "invoke-with-response-stream"
_CANDIDATE_BUFFER_MAXLEN: int = 16

# Required fields for the stream_reconciliation_applied log event.
_APPLIED_REQUIRED_FIELDS: tuple[str, ...] = (
    "gen_ai.request.model",
    "client.id",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "rate_limit.estimated_tokens",
    "rate_limit.aggregated_tokens",
    "rate_limit.reconciliation_delta",
)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _decode_payload_dict(payload: bytes) -> dict[str, object] | None:
    """Decode *payload* as UTF-8 JSON object, or None on failure."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value


def _coerce_token_count(value: object) -> int | None:
    """Return *value* if it is a non-bool int, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _safe_emit(fn: Callable[..., object], *args: object, **kwargs: object) -> None:
    """Invoke *fn* swallowing any exception."""
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        pass


def _last_matching(
    messages: Iterable[EventStreamMessage],
    predicate: Callable[[EventStreamMessage], bool],
) -> EventStreamMessage | None:
    """Return the last message satisfying *predicate*, or None."""
    last: EventStreamMessage | None = None
    for msg in messages:
        if predicate(msg):
            last = msg
    return last


# ---------------------------------------------------------------------------
# StreamTokenReconciler
# ---------------------------------------------------------------------------


class StreamTokenReconciler:
    """Reconcile Shared_TPM_Key after a streaming Bedrock response terminates.

    Wraps the upstream byte iterator with yield-before-parse discipline.
    """

    def __init__(
        self,
        upstream: AsyncIterator[bytes],
        ctx: ReconciliationContext,
        tokens: TokenCounter,
        limiter: RateLimiter,
        parser: EventStreamParser | None = None,
    ) -> None:
        self._upstream = upstream
        self._ctx = ctx
        self._tokens = tokens
        self._limiter = limiter
        self._parser = parser if parser is not None else EventStreamParser()

        self._pending: bytes | None = None
        self._candidates: deque[EventStreamMessage] = deque(maxlen=_CANDIDATE_BUFFER_MAXLEN)

    # ------------------------------------------------------------------
    # Async iteration
    # ------------------------------------------------------------------

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Return the async iterator over forwarded upstream chunks."""
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[bytes]:
        """Yield-before-parse async generator over upstream chunks."""
        try:
            async for chunk in self._upstream:
                # 1. Yield to client FIRST — no added latency.
                yield chunk

                # 2. Single-slot buffer set AFTER yield.
                self._pending = chunk

                # 3. Layer-2 isolation: parser errors swallowed.
                try:
                    messages = self._parser.decode_all(chunk)
                except Exception:
                    messages = []

                # 4. Collect terminal-usage candidates into bounded deque.
                for msg in messages:
                    if self._is_candidate(msg):
                        self._candidates.append(msg)

                # 5. Clear buffer before next upstream read.
                self._pending = None
        except asyncio.CancelledError:
            await self._finalize(StreamOutcome.CLIENT_DISCONNECT)
            raise
        except Exception:
            self._pending = None
            await self._finalize(StreamOutcome.UPSTREAM_ERROR)
            raise
        else:
            await self._finalize(StreamOutcome.COMPLETED)

    # ------------------------------------------------------------------
    # Candidate classification
    # ------------------------------------------------------------------

    def _is_candidate(self, msg: EventStreamMessage) -> bool:
        """Return True iff *msg* is a terminal usage event candidate."""
        return self._parser.is_converse_metadata(msg) or self._parser.is_invoke_metrics_chunk(msg)

    # ------------------------------------------------------------------
    # Finalize — flat sequential checks with early returns
    # ------------------------------------------------------------------

    async def _finalize(self, outcome: StreamOutcome) -> None:
        """Run post-stream reconciliation: validate preconditions, compute and apply delta."""
        try:
            ctx = self._ctx

            if not ctx.rate_ctx_present:
                self._emit_skipped("rate_ctx_absent")
                return

            if ctx.tpm_limit == RATELIMIT_UNLIMITED:
                if outcome == StreamOutcome.COMPLETED:
                    terminal = self._extract_terminal_usage(self._candidates)
                    if terminal is not None:
                        aggregated = self._tokens.calculate_aggregated_tokens(
                            {
                                "inputTokens": terminal.input_tokens,
                                "outputTokens": terminal.output_tokens,
                                "cacheWriteInputTokens": terminal.cache_write_input_tokens,
                            },
                            ctx.model_id,
                        )
                        _safe_emit(
                            record_tokens_consumed,
                            ctx.client_id,
                            ctx.model_id,
                            aggregated,
                            ctx.api_type,
                        )
                self._emit_skipped("tpm_limit_unlimited")
                return

            if outcome != StreamOutcome.COMPLETED:
                self._emit_skipped(outcome.value)
                return

            terminal = self._extract_terminal_usage(self._candidates)
            if terminal is None:
                self._emit_skipped("missing_usage")
                return

            # Compute delta and apply.
            aggregated = self._tokens.calculate_aggregated_tokens(
                {
                    "inputTokens": terminal.input_tokens,
                    "outputTokens": terminal.output_tokens,
                    "cacheWriteInputTokens": terminal.cache_write_input_tokens,
                },
                ctx.model_id,
            )
            delta = aggregated - ctx.estimated_tokens

            applied_emitted = self._emit_applied(terminal, aggregated, delta)

            if applied_emitted:
                _safe_emit(
                    record_stream_reconciliation_delta,
                    ctx.client_id,
                    ctx.model_id,
                    ctx.endpoint,
                    delta,
                )
                _safe_emit(
                    record_tokens_consumed,
                    ctx.client_id,
                    ctx.model_id,
                    aggregated,
                    ctx.api_type,
                )

            if delta != 0:
                shared_tpm_key = f"{{{ctx.client_id}:{ctx.model_id}}}:client:tpm"
                try:
                    await self._limiter.reconcile(shared_tpm_key, delta)
                except Exception as e:  # noqa: BLE001
                    _safe_emit(
                        record_redis_failure,
                        "stream_reconciliation",
                        type(e).__name__,
                    )
                    _safe_emit(
                        logger.error,
                        "Stream reconciliation Redis failure",
                        extra={
                            "event.name": "redis_failure_stream_reconciliation",
                            "gen_ai.request.model": ctx.model_id,
                            "error.message": f"{type(e).__name__}: {e}",
                        },
                    )
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Log-event helpers
    # ------------------------------------------------------------------

    def _emit_skipped(self, reason: str) -> None:
        """Emit stream_reconciliation_skipped log event."""
        _safe_emit(
            logger.info,
            "Stream reconciliation skipped",
            extra={
                "event.name": "stream_reconciliation_skipped",
                "gen_ai.request.model": self._ctx.model_id,
                "client.id": self._ctx.client_id,
                "reason": reason,
            },
        )

    def _missing_applied_fields(
        self, terminal: TerminalUsage, aggregated: int, delta: int
    ) -> list[str]:
        """Return names of required applied-event fields that are None."""
        values: dict[str, object | None] = {
            "gen_ai.request.model": self._ctx.model_id,
            "client.id": self._ctx.client_id,
            "gen_ai.usage.input_tokens": terminal.input_tokens,
            "gen_ai.usage.output_tokens": terminal.output_tokens,
            "rate_limit.estimated_tokens": self._ctx.estimated_tokens,
            "rate_limit.aggregated_tokens": aggregated,
            "rate_limit.reconciliation_delta": delta,
        }
        return [name for name in _APPLIED_REQUIRED_FIELDS if values.get(name) is None]

    def _emit_applied(self, terminal: TerminalUsage, aggregated: int, delta: int) -> bool:
        """Emit stream_reconciliation_applied log event. Returns False if suppressed."""
        missing = self._missing_applied_fields(terminal, aggregated, delta)
        if missing:
            _safe_emit(
                logger.error,
                "Stream reconciliation applied event suppressed: required field missing",
                extra={
                    "event.name": "stream_reconciliation_applied_suppressed",
                    "gen_ai.request.model": self._ctx.model_id,
                    "client.id": self._ctx.client_id,
                    "missing_fields": missing,
                },
            )
            return False
        _safe_emit(
            logger.info,
            "Stream reconciliation applied",
            extra={
                "event.name": "stream_reconciliation_applied",
                "gen_ai.request.model": self._ctx.model_id,
                "client.id": self._ctx.client_id,
                "gen_ai.usage.input_tokens": terminal.input_tokens,
                "gen_ai.usage.output_tokens": terminal.output_tokens,
                "rate_limit.estimated_tokens": self._ctx.estimated_tokens,
                "rate_limit.aggregated_tokens": aggregated,
                "rate_limit.reconciliation_delta": delta,
            },
        )
        return True

    # ------------------------------------------------------------------
    # Terminal-usage extraction dispatch
    # ------------------------------------------------------------------

    def _extract_terminal_usage(
        self, messages: Iterable[EventStreamMessage]
    ) -> TerminalUsage | None:
        """Dispatch extraction by endpoint. Returns None on failure."""
        match self._ctx.endpoint:
            case "converse-stream":
                return self._extract_converse_terminal(messages)
            case "invoke-with-response-stream":
                return self._extract_invoke_terminal(messages)
            case _:
                return None

    def _extract_converse_terminal(
        self, messages: Iterable[EventStreamMessage]
    ) -> TerminalUsage | None:
        """Extract terminal usage from a converse-stream response."""
        candidate = _last_matching(messages, self._parser.is_converse_metadata)
        if candidate is None:
            return None
        payload = _decode_payload_dict(candidate.payload)
        if payload is None:
            return None
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        return self._build_terminal(
            usage.get("inputTokens", 0),
            usage.get("outputTokens", 0),
            usage.get("cacheWriteInputTokens", 0),
        )

    def _extract_invoke_terminal(
        self, messages: Iterable[EventStreamMessage]
    ) -> TerminalUsage | None:
        """Extract terminal usage from an invoke-with-response-stream response."""
        candidate = _last_matching(messages, self._parser.is_invoke_metrics_chunk)
        if candidate is None:
            return None
        payload = _decode_payload_dict(candidate.payload)
        if payload is None:
            return None
        # Unwrap base64 {"bytes":"..."} envelope if metrics not at top level
        if "amazon-bedrock-invocationMetrics" not in payload and "bytes" in payload:
            import base64 as b64
            try:
                payload = json.loads(b64.b64decode(payload["bytes"]))
            except Exception:
                return None
        metrics = payload.get("amazon-bedrock-invocationMetrics")
        if not isinstance(metrics, dict):
            return None
        return self._build_terminal(
            metrics.get("inputTokenCount", 0),
            metrics.get("outputTokenCount", 0),
            metrics.get("cacheWriteInputTokenCount", 0),
        )

    @staticmethod
    def _build_terminal(
        input_raw: object,
        output_raw: object,
        cache_write_raw: object,
    ) -> TerminalUsage | None:
        """Assemble a TerminalUsage from three raw JSON values, or None."""
        input_tokens = _coerce_token_count(input_raw)
        output_tokens = _coerce_token_count(output_raw)
        cache_write_input_tokens = _coerce_token_count(cache_write_raw)
        if input_tokens is None or output_tokens is None or cache_write_input_tokens is None:
            return None
        if (
            input_tokens < 0
            or input_tokens > _INT32_MAX
            or output_tokens < 0
            or output_tokens > _INT32_MAX
            or cache_write_input_tokens < 0
            or cache_write_input_tokens > _INT32_MAX
        ):
            return None
        return TerminalUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_input_tokens=cache_write_input_tokens,
        )
