# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock converse API route using httpx + SigV4 (Phase 3 - clean implementation)."""

import contextlib
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from observability.metrics import MetricsCollector
from services.bedrock_service_httpx import BedrockHttpxService
from util.aws_error_response import create_aws_http_exception
from util.request_body import get_parsed_body


def create_bedrock_httpx_router(
    bedrock_httpx_service: BedrockHttpxService, telemetry: dict
) -> APIRouter:
    """Create Bedrock httpx router with converse endpoint.

    Args:
    ----
        bedrock_httpx_service: BedrockHttpxService instance
        telemetry: Telemetry configuration dict

    Returns:
    -------
        APIRouter with /v1/model/{model_id}/converse endpoint
    """
    router = APIRouter()
    logger = telemetry["logger"]
    metrics = MetricsCollector(telemetry["meter"], telemetry["tracer"], logger)

    @router.post("/model/{model_id}/converse")
    async def converse_httpx(model_id: str, request: Request) -> dict[str, Any]:
        """Converse endpoint using httpx + SigV4 (no boto3 in request path).

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object

        Returns:
        -------
            Bedrock converse API response
        """
        # Extract auth token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("No authorization token provided")
            metrics.record_auth_failure("missing_token")
            raise create_aws_http_exception(
                status_code=403,
                error_code="AccessDenied",
                error_message="Invalid Token",
                request_id="auth-missing-token",
            )
        jwt_token = auth_header[7:]

        # Extract client_id and account_id from middleware state
        claims = getattr(request.state, "jwt_claims", {})
        client_id = claims.get("client_id") or claims.get("sub") or "unknown"

        account_id = None
        if hasattr(request.state, "rate_ctx") and request.state.rate_ctx:
            with contextlib.suppress(TypeError, ValueError):
                _, _, account_id, _, _ = request.state.rate_ctx

        if not account_id:
            raise create_aws_http_exception(
                status_code=403,
                error_code="AccessDenied",
                error_message="No account available",
                request_id="no-account",
            )

        # Get credentials (cached or async STS)
        creds = await bedrock_httpx_service.get_credentials(client_id, account_id, jwt_token)
        if not creds:
            logger.error("Failed to create bedrock client with provided token")
            metrics.record_auth_failure("invalid_token")
            raise create_aws_http_exception(
                status_code=403,
                error_code="AccessDenied",
                error_message="Failed to obtain credentials",
                request_id="sts-failed",
            )

        # Parse body and call Bedrock
        try:
            # Use modified body from guardrail middleware if available
            if hasattr(request.state, "modified_body") and request.state.modified_body:
                body = request.state.modified_body
            else:
                body = await get_parsed_body(request)
            body["modelId"] = model_id

            # Log query information
            messages = body.get("messages", [])
            logger.info(
                "Processing converse request",
                extra={
                    "gen_ai.request.model": model_id,
                    "gen_ai.request.message_count": len(messages),
                    "gen_ai.request.has_system_prompt": bool(body.get("system")),
                    "gen_ai.request.has_tools": bool(body.get("toolConfig")),
                },
            )

            async with metrics.track_request("converse", model_id):
                response = await bedrock_httpx_service.converse(model_id, body, creds)

            # Log successful completion
            usage = response.get("usage", {})
            resp_metrics = response.get("metrics", {})
            logger.info(
                "Converse request completed successfully",
                extra={
                    "gen_ai.request.model": model_id,
                    "gen_ai.usage.input_tokens": usage.get("inputTokens", 0),
                    "gen_ai.usage.output_tokens": usage.get("outputTokens", 0),
                    "gen_ai.duration.model_processing_time_ms": resp_metrics.get("latencyMs", 0),
                    "gen_ai.response.finish_reason": response.get("stopReason"),
                },
            )

            return response

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            error_code = "BedrockError"
            error_msg = ""
            try:
                error_body = e.response.json()
                error_msg = error_body.get("message", "")
                error_code = error_body.get("__type", error_code)
            except Exception:
                error_msg = e.response.text[:200]

            # Provide descriptive error message when Bedrock returns empty message
            if not error_msg or error_msg.strip() == "":
                if status == 403:
                    error_msg = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_msg = f"Bedrock API error: {error_code}"

            logger.warning(
                f"Bedrock converse error for model {model_id}: {error_code} - {error_msg}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_msg,
                    "error.status_code": status,
                },
            )
            raise create_aws_http_exception(
                status_code=status,
                error_code=error_code,
                error_message=error_msg,
                request_id="bedrock-client-error",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Gateway error during converse: {type(e).__name__}: {e}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Converse API failed: {e}",
                request_id="gateway-httpx-error",
            ) from e

    return router
