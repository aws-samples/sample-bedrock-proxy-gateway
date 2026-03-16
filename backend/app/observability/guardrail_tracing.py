# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail tracing utilities."""

from contextlib import asynccontextmanager

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)


@asynccontextmanager
async def guardrail_span():
    """Create a tracing span for guardrail middleware."""
    with tracer.start_as_current_span("guardrail_middleware") as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise
