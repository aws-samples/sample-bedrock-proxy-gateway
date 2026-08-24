# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.rate_limit.eventstream_parser module."""

import json
import struct
import zlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from core.rate_limit.eventstream_parser import (
    ErrorKind,
    EventStreamMessage,
    EventStreamParser,
    Header,
    HeaderType,
    ParseError,
)
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Hypothesis strategies for EventStreamMessage
# ---------------------------------------------------------------------------

# Strategy for header names: 1-20 ASCII printable characters
_header_name_st = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    min_size=1,
    max_size=20,
)

# Strategy for header values by wire type
_bool_true_st = st.just((HeaderType.BOOL_TRUE, True))
_bool_false_st = st.just((HeaderType.BOOL_FALSE, False))
_byte_st = st.integers(min_value=-(2**7), max_value=2**7 - 1).map(lambda v: (HeaderType.BYTE, v))
_short_st = st.integers(min_value=-(2**15), max_value=2**15 - 1).map(
    lambda v: (HeaderType.SHORT, v)
)
_integer_st = st.integers(min_value=-(2**31), max_value=2**31 - 1).map(
    lambda v: (HeaderType.INTEGER, v)
)
_long_st = st.integers(min_value=-(2**63), max_value=2**63 - 1).map(lambda v: (HeaderType.LONG, v))
_byte_array_st = st.binary(min_size=0, max_size=128).map(lambda v: (HeaderType.BYTE_ARRAY, v))
_string_st = st.text(min_size=0, max_size=128).map(lambda v: (HeaderType.STRING, v))
_timestamp_st = st.integers(min_value=0, max_value=2**40).map(
    lambda ms: (
        HeaderType.TIMESTAMP,
        datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=ms),
    )
)
_uuid_st = st.binary(min_size=16, max_size=16).map(lambda b: (HeaderType.UUID, UUID(bytes=b)))

_typed_value_st = st.one_of(
    _bool_true_st,
    _bool_false_st,
    _byte_st,
    _short_st,
    _integer_st,
    _long_st,
    _byte_array_st,
    _string_st,
    _timestamp_st,
    _uuid_st,
)


@st.composite
def _header_st(draw):
    """Strategy to generate a valid Header."""
    name = draw(_header_name_st)
    wire_type, value = draw(_typed_value_st)
    return Header(name=name, wire_type=wire_type, value=value)


@st.composite
def _event_stream_message_st(draw):
    """Strategy to generate an EventStreamMessage with valid headers and payload."""
    headers = draw(st.lists(_header_st(), min_size=0, max_size=5))
    payload = draw(st.binary(min_size=0, max_size=8192))
    return EventStreamMessage(headers=tuple(headers), payload=payload)


# ---------------------------------------------------------------------------
# Feature: streaming-tpm-reconciliation, Property 3: EventStream parser round-trip
# ---------------------------------------------------------------------------


class TestEventStreamParserRoundTrip:
    """Property-based tests for EventStream parser encode/decode round-trip."""

    @settings(max_examples=200, deadline=timedelta(milliseconds=500))
    @given(msgs=st.lists(_event_stream_message_st(), min_size=1, max_size=5))
    def test_property_roundtrip_encode_decode(self, msgs):
        """Property: decode_all(encode_many(msgs)) == msgs."""
        parser = EventStreamParser()
        encoded = parser.encode_many(msgs)
        decoded = parser.decode_all(encoded)

        assert len(decoded) == len(msgs)
        for original, roundtripped in zip(msgs, decoded):
            assert roundtripped.payload == original.payload
            assert len(roundtripped.headers) == len(original.headers)
            for orig_h, rt_h in zip(original.headers, roundtripped.headers):
                assert rt_h.name == orig_h.name
                assert rt_h.wire_type == orig_h.wire_type
                assert rt_h.value == orig_h.value


# ---------------------------------------------------------------------------
# Example tests: ErrorKind cases
# ---------------------------------------------------------------------------


class TestEventStreamParserErrors:
    """Example-based tests for each ErrorKind."""

    @pytest.fixture
    def parser(self):
        """Return a fresh EventStreamParser instance."""
        return EventStreamParser()

    def test_empty_buffer_returns_empty_error(self, parser):
        """Empty buffer -> ErrorKind.EMPTY."""
        with pytest.raises(ParseError) as exc_info:
            parser.decode_all(b"")
        assert exc_info.value.kind == ErrorKind.EMPTY

    def test_truncated_prelude_returns_truncated_error(self, parser):
        """Buffer shorter than prelude (12 bytes) -> ErrorKind.TRUNCATED."""
        with pytest.raises(ParseError) as exc_info:
            parser.decode_all(b"\x00" * 8)
        assert exc_info.value.kind == ErrorKind.TRUNCATED

    def test_length_exceeds_buffer_returns_length_overrun(self, parser):
        """Declared total_length exceeds available bytes -> ErrorKind.LENGTH_OVERRUN."""
        # Build a prelude claiming 1000 bytes total, with valid prelude CRC
        total_length = 1000
        headers_length = 0
        prelude = struct.pack(">II", total_length, headers_length)
        prelude_crc = zlib.crc32(prelude) & 0xFFFFFFFF
        buf = prelude + struct.pack(">I", prelude_crc)
        # buf is only 12 bytes, but claims 1000

        with pytest.raises(ParseError) as exc_info:
            parser.decode_all(buf)
        assert exc_info.value.kind == ErrorKind.LENGTH_OVERRUN

    def test_bad_crc_returns_framing_invalid(self, parser):
        """Corrupted prelude CRC -> ErrorKind.FRAMING_INVALID."""
        # Build a minimal valid message then corrupt the prelude CRC
        msg = EventStreamMessage(headers=(), payload=b"")
        encoded = parser.encode(msg)
        # Corrupt byte 8 (start of prelude CRC)
        corrupted = bytearray(encoded)
        corrupted[8] ^= 0xFF
        buf = bytes(corrupted)

        with pytest.raises(ParseError) as exc_info:
            parser.decode_all(buf)
        assert exc_info.value.kind == ErrorKind.FRAMING_INVALID


# ---------------------------------------------------------------------------
# Example tests: is_converse_metadata and is_invoke_metrics_chunk
# ---------------------------------------------------------------------------


class TestEventStreamParserClassifiers:
    """Tests for terminal usage event classifiers."""

    @pytest.fixture
    def parser(self):
        """Return a fresh EventStreamParser instance."""
        return EventStreamParser()

    def test_is_converse_metadata_non_json_payload(self, parser):
        """Non-JSON payload with :event-type=metadata -> is_converse_metadata returns False."""
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="metadata",
                ),
            ),
            payload=b"not valid json {{{",
        )
        assert parser.is_converse_metadata(msg) is False

    def test_is_converse_metadata_valid(self, parser):
        """Valid metadata event with usage -> returns True."""
        payload = json.dumps({"usage": {"inputTokens": 10, "outputTokens": 20}}).encode()
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="metadata",
                ),
            ),
            payload=payload,
        )
        assert parser.is_converse_metadata(msg) is True

    def test_is_converse_metadata_missing_usage_key(self, parser):
        """Metadata event without 'usage' key -> returns False."""
        payload = json.dumps({"metrics": {"latencyMs": 100}}).encode()
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="metadata",
                ),
            ),
            payload=payload,
        )
        assert parser.is_converse_metadata(msg) is False

    def test_is_invoke_metrics_chunk_non_json_payload(self, parser):
        """Non-JSON payload with :event-type=chunk -> is_invoke_metrics_chunk returns False."""
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="chunk",
                ),
            ),
            payload=b"\x80\x81\x82invalid",
        )
        assert parser.is_invoke_metrics_chunk(msg) is False

    def test_is_invoke_metrics_chunk_valid(self, parser):
        """Valid chunk event with invocationMetrics -> returns True."""
        payload = json.dumps({"amazon-bedrock-invocationMetrics": {"inputTokenCount": 5}}).encode()
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="chunk",
                ),
            ),
            payload=payload,
        )
        assert parser.is_invoke_metrics_chunk(msg) is True

    def test_is_invoke_metrics_chunk_missing_key(self, parser):
        """Chunk event without invocationMetrics key -> returns False."""
        payload = json.dumps({"bytes": "somedata"}).encode()
        msg = EventStreamMessage(
            headers=(
                Header(
                    name=":event-type",
                    wire_type=HeaderType.STRING,
                    value="chunk",
                ),
            ),
            payload=payload,
        )
        assert parser.is_invoke_metrics_chunk(msg) is False
