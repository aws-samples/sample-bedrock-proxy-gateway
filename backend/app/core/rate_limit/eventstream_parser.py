# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""AWS EventStream framing decode/encode.

Stateless codec for the AWS EventStream wire format used by Bedrock streaming
responses. See https://docs.aws.amazon.com/lexv2/latest/dg/event-stream-encoding.html

Public surface:
  - ``HeaderType`` — the 10 wire-type identifiers.
  - ``Header`` / ``EventStreamMessage`` — structured, hashable records.
  - ``ErrorKind`` / ``ParseError`` — framing-error classifications.
  - ``EventStreamParser`` — ``decode_all`` / ``encode`` / ``encode_many``.

Framing layout per message:
  - 12-byte prelude: total_length (u32), headers_length (u32), prelude_crc32 (u32).
  - headers_length bytes of typed headers.
  - Payload bytes (total_length - headers_length - 16).
  - 4-byte message CRC-32 (IEEE).
"""

from __future__ import annotations

import json
import struct
import zlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum, IntEnum
from uuid import UUID

# Header name carrying the event-type discriminator on Bedrock EventStream messages.
_EVENT_TYPE_HEADER = ":event-type"

# AWS EventStream max message size (2**24 bytes).
MAX_BUFFER_SIZE = 16_777_216

# Prelude: total_length (4) + headers_length (4) + prelude_crc32 (4).
_PRELUDE_SIZE = 12
_MESSAGE_CRC_SIZE = 4
_FRAMING_OVERHEAD = _PRELUDE_SIZE + _MESSAGE_CRC_SIZE

# Unix epoch for TIMESTAMP header encode/decode.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class HeaderType(IntEnum):
    """Wire-type identifier for a typed header value (AWS EventStream spec)."""

    BOOL_TRUE = 0
    BOOL_FALSE = 1
    BYTE = 2
    SHORT = 3
    INTEGER = 4
    LONG = 5
    BYTE_ARRAY = 6
    STRING = 7
    TIMESTAMP = 8
    UUID = 9


# Union of every value type ``Header.value`` can carry.
HeaderValue = bool | int | bytes | str | datetime | UUID


@dataclass(frozen=True)
class Header:
    """A single typed header attached to an :class:`EventStreamMessage`."""

    name: str
    wire_type: HeaderType
    value: HeaderValue


@dataclass(frozen=True)
class EventStreamMessage:
    """A decoded EventStream message: ordered headers plus raw payload."""

    headers: tuple[Header, ...]
    payload: bytes


class ErrorKind(str, Enum):
    """Classification of framing failures observed while decoding."""

    EMPTY = "empty"
    TRUNCATED = "truncated"
    LENGTH_OVERRUN = "length-overrun"
    FRAMING_INVALID = "framing-invalid"


@dataclass(frozen=True)
class ParseError(Exception):
    """Structured framing failure raised by :meth:`EventStreamParser.decode_all`."""

    kind: ErrorKind
    offset: int
    detail: str = field(default="")

    def __str__(self) -> str:
        """Return a compact, log-friendly representation."""
        return f"{self.kind.value} at offset {self.offset}: {self.detail}"


class EventStreamParser:
    """Stateless codec for AWS EventStream messages."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode_all(self, buf: bytes) -> list[EventStreamMessage]:
        """Decode all complete EventStream messages in *buf*.

        Raises :class:`ParseError` on the first framing violation.
        """
        if len(buf) > MAX_BUFFER_SIZE:
            raise ParseError(
                kind=ErrorKind.LENGTH_OVERRUN,
                offset=MAX_BUFFER_SIZE,
                detail=f"buffer size {len(buf)} exceeds decoder bound {MAX_BUFFER_SIZE}",
            )

        if len(buf) == 0:
            raise ParseError(
                kind=ErrorKind.EMPTY,
                offset=0,
                detail="empty buffer",
            )

        messages: list[EventStreamMessage] = []
        offset = 0
        total = len(buf)
        while offset < total:
            msg, consumed = self._decode_one(buf, offset)
            messages.append(msg)
            offset += consumed
        return messages

    def encode(self, msg: EventStreamMessage) -> bytes:
        """Encode a single :class:`EventStreamMessage` to wire bytes with valid CRCs."""
        headers_bytes = b"".join(self._encode_header(h) for h in msg.headers)
        headers_length = len(headers_bytes)
        payload_length = len(msg.payload)
        total_length = _FRAMING_OVERHEAD + headers_length + payload_length

        if total_length > MAX_BUFFER_SIZE:
            raise ValueError(f"encoded message length {total_length} exceeds {MAX_BUFFER_SIZE}")

        prelude = struct.pack(">II", total_length, headers_length)
        prelude_crc = zlib.crc32(prelude) & 0xFFFFFFFF
        pre_crc_bytes = prelude + struct.pack(">I", prelude_crc) + headers_bytes + msg.payload
        message_crc = zlib.crc32(pre_crc_bytes) & 0xFFFFFFFF
        return pre_crc_bytes + struct.pack(">I", message_crc)

    def encode_many(self, msgs: Iterable[EventStreamMessage]) -> bytes:
        """Encode a sequence of messages into one concatenated buffer."""
        return b"".join(self.encode(m) for m in msgs)

    # ------------------------------------------------------------------
    # Terminal_Usage_Event classifiers
    # ------------------------------------------------------------------

    def is_converse_metadata(self, msg: EventStreamMessage) -> bool:
        """Return True iff *msg* is a converse-stream terminal usage event.

        Checks for ``:event-type`` == ``"metadata"`` and a ``usage`` payload key.
        """
        if not self._has_event_type(msg, "metadata"):
            return False
        payload = self._decode_json_object(msg.payload)
        return payload is not None and "usage" in payload

    def is_invoke_metrics_chunk(self, msg: EventStreamMessage) -> bool:
        """Return True iff *msg* is an invoke-stream terminal usage event.

        Checks for ``:event-type`` == ``"chunk"`` and an ``amazon-bedrock-invocationMetrics`` key.
        """
        if not self._has_event_type(msg, "chunk"):
            return False
        payload = self._decode_json_object(msg.payload)
        return payload is not None and "amazon-bedrock-invocationMetrics" in payload

    # ------------------------------------------------------------------
    # Internal classifier helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_event_type(msg: EventStreamMessage, expected: str) -> bool:
        """Return True iff *msg* has a ``:event-type`` STRING header equal to *expected*."""
        for header in msg.headers:
            if (
                header.name == _EVENT_TYPE_HEADER
                and header.wire_type is HeaderType.STRING
                and header.value == expected
            ):
                return True
        return False

    @staticmethod
    def _decode_json_object(payload: bytes) -> dict[str, object] | None:
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

    # ------------------------------------------------------------------
    # Internal decode helpers
    # ------------------------------------------------------------------

    def _decode_one(self, buf: bytes, offset: int) -> tuple[EventStreamMessage, int]:
        """Decode a single message starting at *offset*. Returns (message, bytes_consumed)."""
        total = len(buf)
        remaining = total - offset

        if remaining < _PRELUDE_SIZE:
            raise ParseError(
                kind=ErrorKind.TRUNCATED,
                offset=offset,
                detail=f"need {_PRELUDE_SIZE} prelude bytes, have {remaining}",
            )

        total_length, headers_length = struct.unpack_from(">II", buf, offset)
        declared_prelude_crc = struct.unpack_from(">I", buf, offset + 8)[0]

        if total_length > MAX_BUFFER_SIZE:
            raise ParseError(
                kind=ErrorKind.LENGTH_OVERRUN,
                offset=offset,
                detail=f"declared total_length {total_length} exceeds {MAX_BUFFER_SIZE}",
            )

        if total_length < _FRAMING_OVERHEAD:
            raise ParseError(
                kind=ErrorKind.FRAMING_INVALID,
                offset=offset,
                detail=f"declared total_length {total_length} smaller than framing overhead {_FRAMING_OVERHEAD}",
            )

        if total_length > remaining:
            raise ParseError(
                kind=ErrorKind.LENGTH_OVERRUN,
                offset=offset,
                detail=f"declared total_length {total_length} exceeds remaining {remaining}",
            )

        # Verify prelude CRC-32 over the first 8 bytes.
        actual_prelude_crc = zlib.crc32(buf[offset : offset + 8]) & 0xFFFFFFFF
        if actual_prelude_crc != declared_prelude_crc:
            raise ParseError(
                kind=ErrorKind.FRAMING_INVALID,
                offset=offset + 8,
                detail=(
                    f"prelude CRC mismatch: expected "
                    f"{declared_prelude_crc:#010x}, got "
                    f"{actual_prelude_crc:#010x}"
                ),
            )

        # Headers block must fit within the message body.
        max_headers_length = total_length - _FRAMING_OVERHEAD
        if headers_length > max_headers_length:
            raise ParseError(
                kind=ErrorKind.FRAMING_INVALID,
                offset=offset + 4,
                detail=f"headers_length {headers_length} exceeds body capacity {max_headers_length}",
            )

        # Verify message CRC-32.
        message_end = offset + total_length
        pre_crc_bytes = buf[offset : message_end - _MESSAGE_CRC_SIZE]
        declared_message_crc = struct.unpack_from(">I", buf, message_end - _MESSAGE_CRC_SIZE)[0]
        actual_message_crc = zlib.crc32(pre_crc_bytes) & 0xFFFFFFFF
        if actual_message_crc != declared_message_crc:
            raise ParseError(
                kind=ErrorKind.FRAMING_INVALID,
                offset=message_end - _MESSAGE_CRC_SIZE,
                detail=(
                    f"message CRC mismatch: expected "
                    f"{declared_message_crc:#010x}, got "
                    f"{actual_message_crc:#010x}"
                ),
            )

        headers_start = offset + _PRELUDE_SIZE
        payload_start = headers_start + headers_length
        payload_end = message_end - _MESSAGE_CRC_SIZE

        headers = self._decode_headers(buf, headers_start, headers_start + headers_length)
        payload = bytes(buf[payload_start:payload_end])

        return EventStreamMessage(headers=headers, payload=payload), total_length

    def _decode_headers(self, buf: bytes, start: int, end: int) -> tuple[Header, ...]:
        """Decode the header block spanning ``buf[start:end]``."""
        headers: list[Header] = []
        pos = start

        while pos < end:
            # Name length byte
            if pos + 1 > end:
                raise ParseError(
                    kind=ErrorKind.TRUNCATED,
                    offset=pos,
                    detail="header name length byte missing",
                )
            name_length = buf[pos]
            pos += 1

            # Name bytes
            name_end = pos + name_length
            if name_end > end:
                raise ParseError(
                    kind=ErrorKind.TRUNCATED,
                    offset=pos,
                    detail=f"header name declared {name_length} bytes but only {end - pos} remain",
                )
            try:
                name = buf[pos:name_end].decode("ascii")
            except UnicodeDecodeError as e:
                raise ParseError(
                    kind=ErrorKind.FRAMING_INVALID,
                    offset=pos,
                    detail=f"non-ASCII header name: {e}",
                ) from None
            pos = name_end

            # Wire type byte
            if pos + 1 > end:
                raise ParseError(
                    kind=ErrorKind.TRUNCATED,
                    offset=pos,
                    detail="header wire-type byte missing",
                )
            wire_type_byte = buf[pos]
            pos += 1
            try:
                wire_type = HeaderType(wire_type_byte)
            except ValueError:
                raise ParseError(
                    kind=ErrorKind.FRAMING_INVALID,
                    offset=pos - 1,
                    detail=f"unknown header wire type {wire_type_byte}",
                ) from None

            # Value
            value, pos = self._decode_header_value(buf, pos, end, wire_type)
            headers.append(Header(name=name, wire_type=wire_type, value=value))

        return tuple(headers)

    def _decode_header_value(
        self,
        buf: bytes,
        pos: int,
        end: int,
        wire_type: HeaderType,
    ) -> tuple[HeaderValue, int]:
        """Decode a single typed header value starting at *pos*."""
        match wire_type:
            case HeaderType.BOOL_TRUE:
                return True, pos
            case HeaderType.BOOL_FALSE:
                return False, pos
            case HeaderType.BYTE:
                self._require(pos, end, 1, "BYTE header")
                (value,) = struct.unpack_from(">b", buf, pos)
                return value, pos + 1
            case HeaderType.SHORT:
                self._require(pos, end, 2, "SHORT header")
                (value,) = struct.unpack_from(">h", buf, pos)
                return value, pos + 2
            case HeaderType.INTEGER:
                self._require(pos, end, 4, "INTEGER header")
                (value,) = struct.unpack_from(">i", buf, pos)
                return value, pos + 4
            case HeaderType.LONG:
                self._require(pos, end, 8, "LONG header")
                (value,) = struct.unpack_from(">q", buf, pos)
                return value, pos + 8
            case HeaderType.BYTE_ARRAY:
                self._require(pos, end, 2, "BYTE_ARRAY length")
                (length,) = struct.unpack_from(">H", buf, pos)
                pos += 2
                self._require(pos, end, length, "BYTE_ARRAY payload")
                return bytes(buf[pos : pos + length]), pos + length
            case HeaderType.STRING:
                self._require(pos, end, 2, "STRING length")
                (length,) = struct.unpack_from(">H", buf, pos)
                pos += 2
                self._require(pos, end, length, "STRING payload")
                try:
                    value = buf[pos : pos + length].decode("utf-8")
                except UnicodeDecodeError as e:
                    raise ParseError(
                        kind=ErrorKind.FRAMING_INVALID,
                        offset=pos,
                        detail=f"invalid UTF-8 in STRING header value: {e}",
                    ) from None
                return value, pos + length
            case HeaderType.TIMESTAMP:
                self._require(pos, end, 8, "TIMESTAMP header")
                (ms,) = struct.unpack_from(">q", buf, pos)
                value = _EPOCH + timedelta(milliseconds=ms)
                return value, pos + 8
            case HeaderType.UUID:
                self._require(pos, end, 16, "UUID header")
                value = UUID(bytes=bytes(buf[pos : pos + 16]))
                return value, pos + 16

        # Unreachable: HeaderType is closed.
        raise ParseError(
            kind=ErrorKind.FRAMING_INVALID,
            offset=pos,
            detail=f"unhandled wire type {wire_type!r}",
        )

    @staticmethod
    def _require(pos: int, end: int, need: int, what: str) -> None:
        """Assert that *need* bytes remain in the header block."""
        if pos + need > end:
            raise ParseError(
                kind=ErrorKind.TRUNCATED,
                offset=pos,
                detail=f"{what} needs {need} bytes, have {end - pos}",
            )

    # ------------------------------------------------------------------
    # Internal encode helpers
    # ------------------------------------------------------------------

    def _encode_header(self, header: Header) -> bytes:
        """Encode one :class:`Header` to its wire bytes."""
        name_bytes = header.name.encode("ascii")
        if len(name_bytes) > 255:
            raise ValueError(f"header name length {len(name_bytes)} exceeds 255")

        prefix = bytes([len(name_bytes)]) + name_bytes + bytes([int(header.wire_type)])
        value_bytes = self._encode_header_value(header.wire_type, header.value)
        return prefix + value_bytes

    def _encode_header_value(self, wire_type: HeaderType, value: HeaderValue) -> bytes:
        """Encode a header value according to its wire type."""
        match wire_type:
            case HeaderType.BOOL_TRUE:
                return b""
            case HeaderType.BOOL_FALSE:
                return b""
            case HeaderType.BYTE:
                self._require_int(value, -(2**7), 2**7 - 1, "BYTE")
                return struct.pack(">b", value)
            case HeaderType.SHORT:
                self._require_int(value, -(2**15), 2**15 - 1, "SHORT")
                return struct.pack(">h", value)
            case HeaderType.INTEGER:
                self._require_int(value, -(2**31), 2**31 - 1, "INTEGER")
                return struct.pack(">i", value)
            case HeaderType.LONG:
                self._require_int(value, -(2**63), 2**63 - 1, "LONG")
                return struct.pack(">q", value)
            case HeaderType.BYTE_ARRAY:
                if not isinstance(value, bytes | bytearray):
                    raise ValueError(
                        f"BYTE_ARRAY header requires bytes, got {type(value).__name__}"
                    )
                if len(value) > 0xFFFF:
                    raise ValueError(f"BYTE_ARRAY length {len(value)} exceeds 65535")
                return struct.pack(">H", len(value)) + bytes(value)
            case HeaderType.STRING:
                if not isinstance(value, str):
                    raise ValueError(f"STRING header requires str, got {type(value).__name__}")
                encoded = value.encode("utf-8")
                if len(encoded) > 0xFFFF:
                    raise ValueError(f"STRING byte length {len(encoded)} exceeds 65535")
                return struct.pack(">H", len(encoded)) + encoded
            case HeaderType.TIMESTAMP:
                if not isinstance(value, datetime):
                    raise ValueError(
                        f"TIMESTAMP header requires datetime, got {type(value).__name__}"
                    )
                aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
                delta = aware - _EPOCH
                ms = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
                self._require_int(ms, -(2**63), 2**63 - 1, "TIMESTAMP")
                return struct.pack(">q", ms)
            case HeaderType.UUID:
                if not isinstance(value, UUID):
                    raise ValueError(f"UUID header requires uuid.UUID, got {type(value).__name__}")
                return value.bytes

        raise ValueError(f"unhandled wire type {wire_type!r}")

    @staticmethod
    def _require_int(value: object, lo: int, hi: int, what: str) -> None:
        """Assert that *value* is a Python int within [lo, hi]."""
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{what} header requires int, got {type(value).__name__}")
        if not (lo <= value <= hi):
            raise ValueError(f"{what} header value {value} outside [{lo}, {hi}]")
