# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""API Health check module."""

import json

from config import config
from dotenv import load_dotenv
from fastapi import APIRouter, Response
from services.valkey_service import create_valkey_client

health_router = APIRouter()

load_dotenv()


@health_router.get("/health", include_in_schema=False)
async def health():
    """Health check endpoint.

    Returns
    -------
        Response: JSON response with health status, environment, and service information.
    """
    health_info = {
        "status": "healthy",
        "env": config.environment,
        "service": config.otel_service_name,
    }

    return Response(
        content=json.dumps(health_info),
        media_type="application/json",
        status_code=200,
    )


def _create_valkey_response(status: str, message: str) -> Response:
    """Create Valkey health response.

    Args:
    ----
        status: Health status ("healthy" or "unhealthy")
        message: Status message

    Returns:
    -------
        Response: JSON response with Valkey status
    """
    health_info = {"status": status, "service": "valkey", "message": message}
    status_code = 200 if status == "healthy" else 503
    return Response(
        content=json.dumps(health_info),
        media_type="application/json",
        status_code=status_code,
    )


@health_router.get("/health/valkey", include_in_schema=False)
async def valkey_health():
    """Valkey health check endpoint.

    Returns
    -------
        Response: JSON response with Valkey connectivity status.
    """
    try:
        valkey = await create_valkey_client()
        result = await valkey.ping()

        # Decode bytes response if needed
        is_healthy = result == b"PONG" or result == "PONG"

        return _create_valkey_response(
            "healthy" if is_healthy else "unhealthy",
            "Valkey connection successful"
            if is_healthy
            else "Valkey connection check returned unexpected response",
        )
    except TimeoutError:
        return _create_valkey_response("unhealthy", "Valkey connection timed out after 5 seconds")
    except Exception as e:
        return _create_valkey_response("unhealthy", f"Valkey connection failed: {str(e)}")
