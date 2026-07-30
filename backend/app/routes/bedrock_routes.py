# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock API routes using httpx + SigV4 (Phase 3 - clean implementation)."""

import contextlib
from typing import Any

import httpx
import orjson
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from observability.metrics import MetricsCollector
from services.bedrock_service_httpx import BedrockHttpxService
from util.aws_error_response import create_aws_error_json, create_aws_http_exception
from util.request_body import get_parsed_body


def create_bedrock_httpx_router(
    bedrock_httpx_service: BedrockHttpxService, telemetry: dict
) -> APIRouter:
    """Create Bedrock httpx router with all API endpoints.

    Includes converse, converse-stream, invoke, invoke-with-response-stream,
    and apply-guardrail endpoints using httpx + SigV4.

    Args:
    ----
        bedrock_httpx_service: BedrockHttpxService instance
        telemetry: Telemetry configuration dict

    Returns:
    -------
        APIRouter with all Bedrock API endpoints using httpx + SigV4
    """
    router = APIRouter()
    logger = telemetry["logger"]
    metrics = MetricsCollector(telemetry["meter"], telemetry["tracer"], logger)

    async def _get_request_context(request: Request) -> tuple[str, str, str, dict]:
        """Extract auth token, client_id, account_id, and credentials from request.

        Returns
        -------
            Tuple of (jwt_token, client_id, account_id, creds)

        Raises
        ------
            HTTPException: If auth or credentials fail
        """
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

        return jwt_token, client_id, account_id, creds

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
        _, _, _, creds = await _get_request_context(request)

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
        except httpx.RequestError as e:
            logger.warning(f"Network error during converse for model {model_id}: {e}")
            raise create_aws_http_exception(
                status_code=503,
                error_code="ServiceUnavailable",
                error_message=f"Bedrock request failed: {type(e).__name__}",
                request_id="bedrock-network-error",
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

    @router.post("/model/{model_id}/converse-stream")
    async def converse_stream_httpx(model_id: str, request: Request) -> StreamingResponse:
        """Streaming converse endpoint using httpx + SigV4 (no boto3 in request path).

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object

        Returns:
        -------
            StreamingResponse with raw EventStream bytes from Bedrock
        """
        _, _, _, creds = await _get_request_context(request)

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
                "Processing converse-stream request",
                extra={
                    "gen_ai.request.model": model_id,
                    "gen_ai.request.message_count": len(messages),
                    "gen_ai.request.has_system_prompt": bool(body.get("system")),
                    "gen_ai.request.has_tools": bool(body.get("toolConfig")),
                },
            )

            async with metrics.track_stream_request("converse-stream", model_id) as stream_ctx:
                stream_cm = await bedrock_httpx_service.converse_stream(model_id, body, creds)

                async def async_stream_generator():
                    first_chunk = True
                    chunk_count = 0
                    try:
                        async with stream_cm as resp:
                            # Read error body inside async with — the stream
                            # is closed by __aexit__ and unreadable afterwards.
                            if resp.status_code >= 400:
                                try:
                                    body_bytes = await resp.aread()
                                    error_msg = body_bytes[:200].decode(
                                        "utf-8", errors="replace"
                                    )
                                except Exception as read_err:
                                    error_msg = (
                                        f"<unable to read body: "
                                        f"{type(read_err).__name__}: {read_err}>"
                                    )
                                    status_code = resp.status_code
                                    logger.warning(
                                        f"Bedrock streaming error: {status_code} - {error_msg}",
                                        extra={
                                            "gen_ai.request.model": model_id,
                                            "error.type": "BedrockStreamError",
                                            "error.message": error_msg,
                                            "error.status_code": status_code,
                                        },
                                    )
                                    yield create_aws_error_json(
                                        error_code="BedrockError",
                                        error_message=error_msg,
                                        request_id="stream-bedrock-error",
                                    )
                                    return

                            async for chunk in resp.aiter_bytes():
                                if first_chunk:
                                    stream_ctx.record_first_token()
                                    first_chunk = False
                                chunk_count += 1
                                yield chunk

                        logger.info(
                            "Converse-stream request completed successfully",
                            extra={
                                "gen_ai.request.model": model_id,
                                "gen_ai.response.chunks_processed": chunk_count,
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"Gateway error during streaming: {e}",
                            extra={
                                "gen_ai.request.model": model_id,
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
                        )
                        yield create_aws_error_json(
                            error_code="InternalServerError",
                            error_message=str(e),
                            request_id="stream-gateway-error",
                        )

                return StreamingResponse(
                    async_stream_generator(),
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        "Content-Type": "application/vnd.amazon.eventstream",
                        "X-Amzn-Bedrock-Content-Type": "application/json",
                    },
                )

        except httpx.RequestError as e:
            logger.warning(f"Network error during converse-stream for model {model_id}: {e}")
            raise create_aws_http_exception(
                status_code=503,
                error_code="ServiceUnavailable",
                error_message=f"Bedrock request failed: {type(e).__name__}",
                request_id="bedrock-network-error",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Gateway error during converse-stream: {type(e).__name__}: {e}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {e}",
                request_id="stream-gateway-error",
            ) from e

    @router.post("/model/{model_id}/invoke")
    async def invoke_httpx(model_id: str, request: Request) -> dict[str, Any]:
        """InvokeModel endpoint using httpx + SigV4 (no boto3 in request path).

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object

        Returns:
        -------
            Parsed JSON response from Bedrock invoke model API
        """
        _, _, _, creds = await _get_request_context(request)

        try:
            body = await get_parsed_body(request)

            # Extract guardrail config from middleware
            guardrail_config = getattr(request.state, "guardrail_config", None)
            guardrail_params = None
            if guardrail_config:
                guardrail_id = guardrail_config.get("guardrailIdentifier")
                guardrail_version = guardrail_config.get("guardrailVersion")
                if guardrail_id and guardrail_version:
                    logger.info(
                        f"Applying guardrail {guardrail_id} version {guardrail_version} to invoke request"
                    )
                    guardrail_params = guardrail_config

            # Log query information
            logger.info(
                "Processing invoke request",
                extra={
                    "gen_ai.request.model": model_id,
                    "gen_ai.request.content_type": "application/json",
                },
            )


            body_bytes = orjson.dumps(body)

            async with metrics.track_request("invoke", model_id):
                resp_bytes = await bedrock_httpx_service.invoke_model(
                    model_id, body_bytes, creds, guardrail_params
                )

            response_data = orjson.loads(resp_bytes)

            # Log successful completion
            logger.info(
                "Invoke request completed successfully",
                extra={"gen_ai.request.model": model_id},
            )

            return response_data

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

            if not error_msg or error_msg.strip() == "":
                if status == 403:
                    error_msg = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_msg = f"Bedrock API error: {error_code}"

            logger.warning(
                f"Bedrock invoke error for model {model_id}: {error_code} - {error_msg}",
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
                request_id="invoke-bedrock-error",
            ) from e
        except httpx.RequestError as e:
            logger.warning(f"Network error during invoke for model {model_id}: {e}")
            raise create_aws_http_exception(
                status_code=503,
                error_code="ServiceUnavailable",
                error_message=f"Bedrock request failed: {type(e).__name__}",
                request_id="bedrock-network-error",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Gateway error during invoke: {type(e).__name__}: {e}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {e}",
                request_id="invoke-gateway-error",
            ) from e

    @router.post("/model/{model_id}/invoke-with-response-stream")
    async def invoke_stream_httpx(model_id: str, request: Request) -> StreamingResponse:
        """InvokeModelWithResponseStream endpoint using httpx + SigV4.

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object

        Returns:
        -------
            StreamingResponse with raw EventStream bytes from Bedrock
        """
        _, _, _, creds = await _get_request_context(request)

        try:
            body = await get_parsed_body(request)

            # Extract guardrail config from middleware
            guardrail_config = getattr(request.state, "guardrail_config", None)
            guardrail_params = None
            if guardrail_config:
                guardrail_id = guardrail_config.get("guardrailIdentifier")
                guardrail_version = guardrail_config.get("guardrailVersion")
                if guardrail_id and guardrail_version:
                    logger.info(
                        f"Applying guardrail {guardrail_id} version {guardrail_version} to invoke-stream request"
                    )
                    guardrail_params = guardrail_config

            # Log query information
            logger.info(
                "Processing invoke-stream request",
                extra={
                    "gen_ai.request.model": model_id,
                    "gen_ai.request.content_type": "application/json",
                },
            )


            body_bytes = orjson.dumps(body)

            async with metrics.track_stream_request("invoke-stream", model_id) as stream_ctx:
                stream_cm = await bedrock_httpx_service.invoke_model_stream(
                    model_id, body_bytes, creds, guardrail_params
                )

                async def async_stream_generator():
                    first_chunk = True
                    chunk_count = 0
                    try:
                        async with stream_cm as resp:
                            # Read error body inside async with — stream is
                            # closed by __aexit__ and unreadable afterwards.
                            if resp.status_code >= 400:
                                try:
                                    error_body_bytes = await resp.aread()
                                    error_msg = error_body_bytes[:200].decode(
                                        "utf-8", errors="replace"
                                    )
                                except Exception as read_err:
                                    error_msg = (
                                        f"<unable to read body: "
                                        f"{type(read_err).__name__}: {read_err}>"
                                    )
                                    status_code = resp.status_code
                                    logger.warning(
                                        f"Bedrock invoke-stream error: {status_code} - {error_msg}",
                                        extra={
                                            "gen_ai.request.model": model_id,
                                            "error.type": "BedrockStreamError",
                                            "error.message": error_msg,
                                            "error.status_code": status_code,
                                        },
                                    )
                                    stream_ctx.record_failure(
                                        httpx.HTTPStatusError(
                                            f"Bedrock error {status_code}",
                                            request=resp.request,
                                            response=resp,
                                        )
                                    )
                                    yield create_aws_error_json(
                                        error_code="BedrockError",
                                        error_message=error_msg,
                                        request_id="invoke-stream-bedrock-error",
                                    )
                                    return

                            async for chunk in resp.aiter_bytes():
                                if first_chunk:
                                    stream_ctx.record_first_token()
                                    first_chunk = False
                                chunk_count += 1
                                yield chunk

                        logger.info(
                            "Invoke-stream request completed successfully",
                            extra={
                                "gen_ai.request.model": model_id,
                                "gen_ai.response.chunks_processed": chunk_count,
                            },
                        )
                    except Exception as e:
                        logger.error(
                            f"Gateway error during invoke-stream: {e}",
                            extra={
                                "gen_ai.request.model": model_id,
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
                        )
                        stream_ctx.record_failure(e)
                        yield create_aws_error_json(
                            error_code="InternalServerError",
                            error_message=str(e),
                            request_id="invoke-stream-gateway-error",
                        )

                return StreamingResponse(
                    async_stream_generator(),
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                        "Content-Type": "application/vnd.amazon.eventstream",
                        "X-Amzn-Bedrock-Content-Type": "application/json",
                    },
                )

        except httpx.RequestError as e:
            logger.warning(f"Network error during invoke-stream for model {model_id}: {e}")
            raise create_aws_http_exception(
                status_code=503,
                error_code="ServiceUnavailable",
                error_message=f"Bedrock request failed: {type(e).__name__}",
                request_id="bedrock-network-error",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Gateway error during invoke-stream: {type(e).__name__}: {e}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {e}",
                request_id="invoke-stream-gateway-error",
            ) from e

    @router.post("/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply")
    async def apply_guardrail_httpx(
        guardrail_identifier: str,
        guardrail_version: str,
        request: Request,
    ) -> dict[str, Any]:
        """Apply guardrail endpoint using httpx + SigV4 (no boto3 in request path).

        Args:
        ----
            guardrail_identifier: Guardrail identifier (logical or actual ID)
            guardrail_version: Guardrail version
            request: FastAPI request object

        Returns:
        -------
            Bedrock apply guardrail API response
        """
        _, _, _, creds = await _get_request_context(request)

        try:
            body = await get_parsed_body(request)

            # Log request information
            logger.info(
                "Processing apply guardrail request",
                extra={
                    "guardrail.identifier": guardrail_identifier,
                    "guardrail.version": guardrail_version,
                    "guardrail.content_count": len(body.get("content", [])),
                    "guardrail.output_scope": body.get("outputScope"),
                    "guardrail.source": body.get("source"),
                },
            )

            # Get resolved guardrail IDs from middleware
            resolved_guardrail = getattr(request.state, "resolved_guardrail", None)
            if not resolved_guardrail:
                logger.warning(
                    f"Guardrail '{guardrail_identifier}' not found",
                    extra={
                        "guardrail.identifier": guardrail_identifier,
                        "error.type": "GuardrailNotFound",
                    },
                )
                raise create_aws_http_exception(
                    status_code=404,
                    error_code="NotFoundException",
                    error_message=f"Guardrail '{guardrail_identifier}' not found",
                    request_id="apply-guardrail-not-found",
                )

            actual_guardrail_id = resolved_guardrail["guardrailIdentifier"]
            actual_guardrail_version = resolved_guardrail["guardrailVersion"]
            logger.info(
                f"Resolved logical guardrail ID '{guardrail_identifier}' to actual ID "
                f"'{actual_guardrail_id}' version '{actual_guardrail_version}'"
            )

            # Build body for Bedrock exclude guardrail identifiers (they're in the URL)
            apply_body = {
                k: v
                for k, v in body.items()
                if k not in ("guardrailIdentifier", "guardrailVersion") and v is not None
            }

            async with metrics.track_request("apply_guardrail", guardrail_identifier):
                response = await bedrock_httpx_service.apply_guardrail(
                    actual_guardrail_id, actual_guardrail_version, apply_body, creds
                )

            # Log successful completion
            logger.info(
                "Apply guardrail request completed successfully",
                extra={
                    "guardrail.identifier": actual_guardrail_id,
                    "guardrail.version": actual_guardrail_version,
                    "guardrail.action": response.get("action"),
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

            if not error_msg or error_msg.strip() == "":
                error_msg = f"Bedrock API error: {error_code}"

            logger.warning(
                f"Bedrock apply guardrail error: {error_code} - {error_msg}",
                extra={
                    "guardrail.identifier": guardrail_identifier,
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
                request_id="apply-guardrail-bedrock-error",
            ) from e
        except httpx.RequestError as e:
            logger.warning(f"Network error during apply guardrail {guardrail_identifier}: {e}")
            raise create_aws_http_exception(
                status_code=503,
                error_code="ServiceUnavailable",
                error_message=f"Bedrock request failed: {type(e).__name__}",
                request_id="bedrock-network-error",
            ) from e
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Gateway error during apply guardrail: {type(e).__name__}: {e}",
                extra={
                    "guardrail.identifier": guardrail_identifier,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Apply guardrail API failed: {e}",
                request_id="apply-guardrail-gateway-error",
            ) from e

    return router
