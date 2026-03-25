# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request body parsing with orjson for single-parse optimization."""

import orjson
from fastapi import Request


async def get_parsed_body(request: Request) -> dict:
    """Get parsed JSON body from request, parsing only once with orjson.

    First call reads and parses the body, storing results in request.state.
    Subsequent calls return the cached parsed body.
    """
    cached = getattr(request.state, "parsed_body", None)
    if isinstance(cached, dict):
        return cached

    raw = await request.body()
    parsed = orjson.loads(raw) if raw else {}
    request.state.raw_body = raw
    request.state.parsed_body = parsed
    return parsed
