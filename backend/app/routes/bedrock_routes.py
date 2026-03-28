# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock API routes for Bedrock Gateway."""

import base64
from typing import Any

from fastapi import APIRouter, Request
from observability.metrics import MetricsCollector
from services.bedrock_service import BedrockService
from util.aws_error_response import create_aws_http_exception


def create_bedrock_router(bedrock_service: BedrockService, telemetry: dict) -> APIRouter:
    """Create Bedrock API router with service dependency.

    Args:
    ----
        bedrock_service: BedrockService instance for client management
        telemetry: Telemetry configuration containing tracer, meter, and logger

    Returns:
    -------
        APIRouter: Configured bedrock router with all endpoints
    """
    bedrock_router = APIRouter()

    tracer = telemetry["tracer"]
    meter = telemetry["meter"]
    logger = telemetry["logger"]

    # Initialize metrics collector
    metrics = MetricsCollector(meter, tracer, logger)

    def decode_base64_bytes(obj):
        """Recursively decode base64 bytes in the request object."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "bytes" and isinstance(value, str):
                    obj[key] = base64.b64decode(value)
                else:
                    decode_base64_bytes(value)
        elif isinstance(obj, list):
            for item in obj:
                decode_base64_bytes(item)

    async def get_bedrock_client(request: Request) -> Any:
        """Dependency to get and validate bedrock client.

        Args:
        ----
            request: FastAPI request object

        Returns:
        -------
            Any: Validated bedrock runtime client

        Raises:
        ------
            HTTPException: If authentication fails or client creation fails
        """
        # Extract JWT token for shared account access
        auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")

        if not auth_token:
            logger.warning("No authorization token provided")
            metrics.record_auth_failure("missing_token")
            raise create_aws_http_exception(
                status_code=403,
                error_code="AccessDenied",
                error_message="Invalid Token",
                request_id="auth-missing-token",
            )

        logger.debug("Bedrock client validated successfully")

        # Extract account_id from rate limiting context
        account_id = None
        if hasattr(request.state, "rate_ctx") and request.state.rate_ctx:
            try:
                # The line below unpacks a 5 element tuple but only keeps the 3rd element --> account_id
                # The rate_ctx structure looks like the below:
                # request.state.rate_ctx = (
                #     client_id,        # Position 0 - ignored with _
                #     model_id,         # Position 1 - ignored with _
                #     account_id,       # Position 2 - extracted
                #     quota_config.tpm, # Position 3 - ignored with _
                #     api_type,         # Position 4 - ignored with _
                # )
                _, _, account_id, _, _ = request.state.rate_ctx
            except (TypeError, ValueError):
                # rate_ctx is not a tuple or doesn't have enough elements
                account_id = None

        # Attempt to create client using account selected by rate limiting
        # This enables multi-account cost distribution and quota isolation
        jwt_claims = getattr(request.state, "jwt_claims", None)
        bedrock_client = await bedrock_service.get_authenticated_client(
            auth_token, account_id, jwt_claims
        )
        if bedrock_client is None:
            logger.error("Failed to create bedrock client with provided token")
            metrics.record_auth_failure("invalid_token")
            raise create_aws_http_exception(
                status_code=403,
                error_code="AccessDenied",
                error_message="Invalid Token",
                request_id="auth-invalid-token",
            )

        return bedrock_client

    # NOTE: converse endpoint moved to bedrock_routes1.py (httpx + SigV4 implementation)
    # @bedrock_router.post("/model/{model_id}/converse")
    # async def converse_proxy(...): ...

    # NOTE: converse-stream endpoint moved to bedrock_routes1.py (httpx + SigV4 implementation)
    # @bedrock_router.post("/model/{model_id}/converse-stream")
    # async def converse_stream_proxy(...): ...

    # NOTE: invoke endpoint moved to bedrock_routes1.py (httpx + SigV4 implementation)
    # @bedrock_router.post("/model/{model_id}/invoke")
    # async def invoke_model_proxy(...): ...

    # NOTE: invoke-with-response-stream endpoint moved to bedrock_routes1.py (httpx + SigV4)
    # @bedrock_router.post("/model/{model_id}/invoke-with-response-stream")
    # async def invoke_model_stream_proxy(...): ...

    # NOTE: apply_guardrail endpoint moved to bedrock_routes1.py (httpx + SigV4 implementation)
    # @bedrock_router.post("/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply")
    # async def apply_guardrail(...): ...

    return bedrock_router
