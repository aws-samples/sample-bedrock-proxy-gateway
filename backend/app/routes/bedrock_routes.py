"""Bedrock API routes for Bedrock Gateway."""

import base64
import json
from typing import Any

from botocore.exceptions import ClientError, ParamValidationError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from observability.metrics import MetricsCollector
from services.bedrock_service import BedrockService
from util.aws_error_response import create_aws_error_json, create_aws_http_exception


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
        bedrock_client = await bedrock_service.get_authenticated_client(auth_token, account_id)
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

    @bedrock_router.post("/model/{model_id}/converse")
    async def converse_proxy(
        model_id: str,
        request: Request,
        bedrock_client=Depends(get_bedrock_client),  # noqa: B008
    ) -> dict[str, Any]:
        """Proxy endpoint for converse APIs.

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object
            bedrock_client: Validated bedrock runtime client dependency

        Returns:
        -------
            dict[str, Any]: Bedrock converse API response

        Raises:
        ------
            HTTPException: If the converse API call fails
        """
        try:
            async with metrics.track_request("converse", model_id):
                # Use modified body from guardrail middleware if available
                if hasattr(request.state, "modified_body") and request.state.modified_body:
                    body = request.state.modified_body
                else:
                    # Parse JSON and decode base64 bytes
                    body_bytes = await request.body()
                    body = json.loads(body_bytes.decode("utf-8"))

                decode_base64_bytes(body)
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

                # Call Bedrock converse API
                async with bedrock_client as client:
                    response = await client.converse(**body)

                # Log successful completion
                usage = response.get("usage", {})
                resp_metrics = response.get("metrics", {})
                logger.info(
                    "Converse request completed successfully",
                    extra={
                        "gen_ai.request.model": model_id,
                        "gen_ai.usage.input_tokens": usage.get("inputTokens", 0),
                        "gen_ai.usage.output_tokens": usage.get("outputTokens", 0),
                        "gen_ai.duration.model_processing_time_ms": resp_metrics.get(
                            "latencyMs", 0
                        ),
                        "gen_ai.response.finish_reason": response.get("stopReason"),
                    },
                )

                return response
        except HTTPException:
            # Re-raise HTTPException to preserve original status code (e.g., 403 from rate limiting)
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raw_error_message = e.response["Error"].get("Message", "")
            status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            # Provide descriptive error message when AWS returns empty message
            if not raw_error_message or raw_error_message.strip() == "":
                if status_code == 403:
                    error_message = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_message = f"Bedrock API error: {error_code}"
            else:
                error_message = raw_error_message

            logger.warning(
                f"Bedrock converse API error for model {model_id}: {error_code} - {error_message}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_message,
                    "error.status_code": status_code,
                },
            )
            raise create_aws_http_exception(
                status_code=status_code,
                error_code=error_code,
                error_message=error_message,
                request_id="bedrock-client-error",
            ) from e
        except ParamValidationError as e:
            logger.warning(
                f"Parameter validation error for converse API: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "ParamValidationError",
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=400,
                error_code="ValidationException",
                error_message=str(e),
                request_id="param-validation-error",
            ) from e
        except Exception as e:
            logger.error(
                f"Gateway error during converse API call for model {model_id}: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Converse API failed: {str(e)}",
                request_id="gateway-error",
            ) from e

    @bedrock_router.post("/model/{model_id}/converse-stream")
    async def converse_stream_proxy(
        model_id: str,
        request: Request,
        bedrock_client=Depends(get_bedrock_client),  # noqa: B008
    ) -> StreamingResponse:
        """Proxy endpoint for streaming conversational responses.

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object
            bedrock_client: Validated bedrock runtime client dependency

        Returns:
        -------
            StreamingResponse: Streaming response from Bedrock converse stream API

        Raises:
        ------
            HTTPException: If the converse stream API call fails
        """
        try:
            async with metrics.track_stream_request("converse-stream", model_id) as stream_ctx:
                # Use modified body from guardrail middleware if available
                if hasattr(request.state, "modified_body") and request.state.modified_body:
                    body = request.state.modified_body
                else:
                    # Parse JSON and decode base64 bytes
                    body_bytes = await request.body()
                    body = json.loads(body_bytes.decode("utf-8"))

                decode_base64_bytes(body)
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

                # Call Bedrock converse stream API
                async with bedrock_client as client:
                    response = await client.converse_stream(**body)

                def stream_generator():
                    first_chunk = True
                    chunk_count = 0
                    try:
                        stream_body = response.get("stream")
                        if stream_body:
                            # Process streaming response chunks
                            for chunk in stream_body._raw_stream.stream():
                                # Record TTFT metric on first chunk for monitoring
                                if first_chunk:
                                    stream_ctx.record_first_token()
                                    first_chunk = False
                                chunk_count += 1
                                yield chunk

                            # Log successful completion
                            logger.info(
                                "Converse-stream request completed successfully",
                                extra={
                                    "gen_ai.request.model": model_id,
                                    "gen_ai.response.chunks_processed": chunk_count,
                                },
                            )
                        else:
                            logger.error(
                                "No stream body in response",
                                extra={
                                    "gen_ai.request.model": model_id,
                                    "error.type": "NoStreamBody",
                                },
                            )
                            error_data = create_aws_error_json(
                                error_code="InternalServerError",
                                error_message="No stream body in response",
                                request_id="stream-no-body",
                            )
                            yield error_data
                    except ClientError as e:
                        error_code = e.response["Error"]["Code"]
                        raw_error_message = e.response["Error"].get("Message", "")
                        status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

                        # Provide descriptive error message when AWS returns empty message
                        if not raw_error_message or raw_error_message.strip() == "":
                            if status_code == 403:
                                error_message = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                            else:
                                error_message = f"Bedrock API error: {error_code}"
                        else:
                            error_message = raw_error_message

                        logger.warning(
                            f"Bedrock streaming error: {error_code} - {error_message}",
                            extra={
                                "gen_ai.request.model": model_id,
                                "error.type": "BedrockClientError",
                                "error.code": error_code,
                                "error.message": error_message,
                            },
                        )
                        error_data = create_aws_error_json(
                            error_code=error_code,
                            error_message=error_message,
                            request_id="stream-bedrock-error",
                        )
                        yield error_data
                    except Exception as e:
                        logger.error(
                            f"Gateway error during streaming: {e}",
                            extra={
                                "gen_ai.request.model": model_id,
                                "error.type": type(e).__name__,
                                "error.message": str(e),
                            },
                        )
                        error_data = create_aws_error_json(
                            error_code="InternalServerError",
                            error_message=str(e),
                            request_id="stream-gateway-error",
                        )
                        yield error_data

                return StreamingResponse(
                    stream_generator(),
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                        "Content-Type": "application/vnd.amazon.eventstream",
                        "Transfer-Encoding": "chunked",
                        "X-Amzn-Bedrock-Content-Type": "application/json",
                    },
                )
        except HTTPException:
            # Re-raise HTTPException to preserve original status code (e.g., 403 from rate limiting)
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raw_error_message = e.response["Error"].get("Message", "")
            status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            # Provide descriptive error message when AWS returns empty message
            if not raw_error_message or raw_error_message.strip() == "":
                if status_code == 403:
                    error_message = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_message = f"Bedrock API error: {error_code}"
            else:
                error_message = raw_error_message

            logger.warning(
                f"Bedrock converse-stream API error for model {model_id}: {error_code} - {error_message}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_message,
                    "error.status_code": status_code,
                },
            )
            raise create_aws_http_exception(
                status_code=status_code,
                error_code=error_code,
                error_message=error_message,
                request_id="bedrock-stream-error",
            ) from e
        except ParamValidationError as e:
            logger.warning(
                f"Parameter validation error for converse-stream API: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "ParamValidationError",
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=400,
                error_code="ValidationException",
                error_message=str(e),
                request_id="stream-validation-error",
            ) from e
        except Exception as e:
            logger.error(
                f"Gateway error during converse-stream API call for model {model_id}: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {str(e)}",
                request_id="stream-gateway-error",
            ) from e

    @bedrock_router.post("/model/{model_id}/invoke")
    async def invoke_model_proxy(
        model_id: str,
        request: Request,
        bedrock_client=Depends(get_bedrock_client),  # noqa: B008
    ) -> dict[str, Any]:
        """Proxy endpoint for InvokeModel API.

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object
            bedrock_client: Validated bedrock runtime client dependency

        Returns:
        -------
            dict[str, Any]: Parsed JSON response from Bedrock invoke model API

        Raises:
        ------
            HTTPException: If the invoke model API call fails
        """
        try:
            async with metrics.track_request("invoke", model_id):
                body = await request.json()

                # Add guardrail config from headers if available
                guardrail_config = getattr(request.state, "guardrail_config", None)
                if guardrail_config:
                    # Add guardrail headers for invoke API
                    guardrail_id = guardrail_config.get("guardrailIdentifier")
                    guardrail_version = guardrail_config.get("guardrailVersion")
                    if guardrail_id and guardrail_version:
                        logger.info(
                            f"Applying guardrail {guardrail_id} version {guardrail_version} to invoke request"
                        )

                model_body = json.dumps(body)
                content_type = "application/json"
                accept = "application/json"

                # Log query information
                logger.info(
                    "Processing invoke request",
                    extra={
                        "gen_ai.request.model": model_id,
                        "gen_ai.request.content_type": content_type,
                    },
                )

                # BotocoreInstrumentor automatically traces this call
                async with bedrock_client as client:
                    invoke_params = {
                        "modelId": model_id,
                        "body": model_body,
                        "contentType": content_type,
                        "accept": accept,
                    }

                    # Add guardrail parameters if available
                    if guardrail_config:
                        guardrail_id = guardrail_config.get("guardrailIdentifier")
                        guardrail_version = guardrail_config.get("guardrailVersion")
                        if guardrail_id and guardrail_version:
                            invoke_params["guardrailIdentifier"] = guardrail_id
                            invoke_params["guardrailVersion"] = guardrail_version
                            if guardrail_config.get("trace"):
                                invoke_params["trace"] = guardrail_config["trace"]

                    response = await client.invoke_model(**invoke_params)

                response_data = json.loads(response["body"].read())

                # Log successful completion
                logger.info(
                    "Invoke request completed successfully",
                    extra={"gen_ai.request.model": model_id},
                )

                return response_data
        except HTTPException:
            # Re-raise HTTPException to preserve original status code (e.g., 403 from rate limiting)
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raw_error_message = e.response["Error"].get("Message", "")
            status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            # Provide descriptive error message when AWS returns empty message
            if not raw_error_message or raw_error_message.strip() == "":
                if status_code == 403:
                    error_message = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_message = f"Bedrock API error: {error_code}"
            else:
                error_message = raw_error_message

            logger.warning(
                f"Bedrock invoke API error for model {model_id}: {error_code} - {error_message}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_message,
                    "error.status_code": status_code,
                },
            )
            raise create_aws_http_exception(
                status_code=status_code,
                error_code=error_code,
                error_message=error_message,
                request_id="invoke-bedrock-error",
            ) from e
        except ParamValidationError as e:
            logger.warning(
                f"Parameter validation error for invoke API: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "ParamValidationError",
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=400,
                error_code="ValidationException",
                error_message=str(e),
                request_id="invoke-validation-error",
            ) from e
        except Exception as e:
            logger.error(
                f"Gateway error during invoke API call for model {model_id}: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {str(e)}",
                request_id="invoke-gateway-error",
            ) from e

    @bedrock_router.post("/model/{model_id}/invoke-with-response-stream")
    async def invoke_model_stream_proxy(
        model_id: str,
        request: Request,
        bedrock_client=Depends(get_bedrock_client),  # noqa: B008
    ) -> StreamingResponse:
        """Proxy endpoint for InvokeModelWithResponseStream API.

        Args:
        ----
            model_id: Bedrock model identifier
            request: FastAPI request object
            bedrock_client: Validated bedrock runtime client dependency

        Returns:
        -------
            StreamingResponse: Streaming response from Bedrock invoke model stream API

        Raises:
        ------
            HTTPException: If the invoke model stream API call fails
        """
        try:
            async with metrics.track_stream_request("invoke-stream", model_id) as stream_ctx:
                body = await request.json()

                # Add guardrail config from headers if available
                guardrail_config = getattr(request.state, "guardrail_config", None)
                if guardrail_config:
                    # Add guardrail headers for invoke-stream API
                    guardrail_id = guardrail_config.get("guardrailIdentifier")
                    guardrail_version = guardrail_config.get("guardrailVersion")
                    if guardrail_id and guardrail_version:
                        logger.info(
                            f"Applying guardrail {guardrail_id} version {guardrail_version} to invoke-stream request"
                        )

                model_body = json.dumps(body)
                content_type = "application/json"
                accept = "application/json"

                # Log query information
                logger.info(
                    "Processing invoke-stream request",
                    extra={
                        "gen_ai.request.model": model_id,
                        "gen_ai.request.content_type": content_type,
                    },
                )

                async def stream_generator():
                    first_chunk = True
                    chunk_count = 0
                    try:
                        # BotocoreInstrumentor automatically traces this call
                        async with bedrock_client as client:
                            invoke_params = {
                                "modelId": model_id,
                                "body": model_body,
                                "contentType": content_type,
                                "accept": accept,
                            }

                            # Add guardrail parameters if available
                            if guardrail_config:
                                guardrail_id = guardrail_config.get("guardrailIdentifier")
                                guardrail_version = guardrail_config.get("guardrailVersion")
                                if guardrail_id and guardrail_version:
                                    invoke_params["guardrailIdentifier"] = guardrail_id
                                    invoke_params["guardrailVersion"] = guardrail_version
                                    if guardrail_config.get("trace"):
                                        invoke_params["trace"] = guardrail_config["trace"]

                            response = await client.invoke_model_with_response_stream(
                                **invoke_params
                            )

                        stream_body = response["body"]
                        for chunk in stream_body._raw_stream.stream():
                            if first_chunk:
                                stream_ctx.record_first_token()
                                first_chunk = False

                            chunk_count += 1
                            yield chunk

                        # Log successful completion
                        logger.info(
                            "Invoke-stream request completed successfully",
                            extra={
                                "gen_ai.request.model": model_id,
                                "gen_ai.response.chunks_processed": chunk_count,
                            },
                        )
                    except ClientError as e:
                        error_code = e.response["Error"]["Code"]
                        error_message = e.response["Error"]["Message"]

                        logger.warning(
                            f"Bedrock invoke-stream error: {error_code} - {error_message}",
                            extra={
                                "gen_ai.request.model": model_id,
                                "error.type": "BedrockClientError",
                                "error.code": error_code,
                                "error.message": error_message,
                            },
                        )
                        stream_ctx.record_failure(e)
                        error_data = create_aws_error_json(
                            error_code=error_code,
                            error_message=error_message or f"Bedrock API error: {error_code}",
                            request_id="invoke-stream-bedrock-error",
                        )
                        yield error_data
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
                        error_data = create_aws_error_json(
                            error_code="InternalServerError",
                            error_message=str(e),
                            request_id="invoke-stream-gateway-error",
                        )
                        yield error_data

                return StreamingResponse(
                    stream_generator(),
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                        "Content-Type": "application/vnd.amazon.eventstream",
                        "Transfer-Encoding": "chunked",
                        "X-Amzn-Bedrock-Content-Type": "application/json",
                    },
                )
        except HTTPException:
            # Re-raise HTTPException to preserve original status code (e.g., 403 from rate limiting)
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raw_error_message = e.response["Error"].get("Message", "")
            status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            # Provide descriptive error message when AWS returns empty message
            if not raw_error_message or raw_error_message.strip() == "":
                if status_code == 403:
                    error_message = f"Access denied for model '{model_id}'. Model may not be enabled in your account or region."
                else:
                    error_message = f"Bedrock API error: {error_code}"
            else:
                error_message = raw_error_message

            logger.warning(
                f"Bedrock invoke-stream API error for model {model_id}: {error_code} - {error_message}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_message,
                    "error.status_code": status_code,
                },
            )
            raise create_aws_http_exception(
                status_code=status_code,
                error_code=error_code,
                error_message=error_message,
                request_id="invoke-stream-error",
            ) from e
        except ParamValidationError as e:
            logger.warning(
                f"Parameter validation error for invoke-stream API: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": "ParamValidationError",
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=400,
                error_code="ValidationException",
                error_message=str(e),
                request_id="invoke-stream-validation-error",
            ) from e
        except Exception as e:
            logger.error(
                f"Gateway error during invoke-stream API call for model {model_id}: {str(e)}",
                extra={
                    "gen_ai.request.model": model_id,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Gateway error: {str(e)}",
                request_id="invoke-stream-gateway-error",
            ) from e

    @bedrock_router.post("/guardrail/{guardrail_identifier}/version/{guardrail_version}/apply")
    async def apply_guardrail(
        guardrail_identifier: str,
        guardrail_version: str,
        request: Request,
        bedrock_client=Depends(get_bedrock_client),  # noqa: B008
    ) -> dict[str, Any]:
        """Apply guardrail to content.

        Args:
        ----
            guardrail_identifier: Guardrail identifier (logical or actual ID)
            guardrail_version: Guardrail version
            request: FastAPI request object
            bedrock_client: Validated bedrock runtime client dependency

        Returns:
        -------
            dict[str, Any]: Bedrock apply guardrail API response

        Raises:
        ------
            HTTPException: If the apply guardrail API call fails
        """
        try:
            async with metrics.track_request("apply_guardrail", guardrail_identifier):
                # Parse request body
                body = await request.json()

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
                    f"Resolved logical guardrail ID '{guardrail_identifier}' to actual ID '{actual_guardrail_id}' version '{actual_guardrail_version}'"
                )

                # Call Bedrock apply guardrail API
                async with bedrock_client as client:
                    apply_params = {
                        "guardrailIdentifier": actual_guardrail_id,
                        "guardrailVersion": actual_guardrail_version,
                    }

                    # Add all body parameters except guardrail identifiers
                    for key, value in body.items():
                        if (
                            key not in ["guardrailIdentifier", "guardrailVersion"]
                            and value is not None
                        ):
                            apply_params[key] = value

                    response = await client.apply_guardrail(**apply_params)

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
        except HTTPException:
            # Re-raise HTTPException to preserve original status code
            raise
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            raw_error_message = e.response["Error"].get("Message", "")
            status_code = e.response["ResponseMetadata"]["HTTPStatusCode"]

            # Provide descriptive error message when AWS returns empty message
            if not raw_error_message or raw_error_message.strip() == "":
                error_message = f"Bedrock API error: {error_code}"
            else:
                error_message = raw_error_message

            logger.warning(
                f"Bedrock apply guardrail API error: {error_code} - {error_message}",
                extra={
                    "guardrail.identifier": guardrail_identifier,
                    "error.type": "BedrockClientError",
                    "error.code": error_code,
                    "error.message": error_message,
                    "error.status_code": status_code,
                },
            )
            raise create_aws_http_exception(
                status_code=status_code,
                error_code=error_code,
                error_message=error_message,
                request_id="apply-guardrail-bedrock-error",
            ) from e
        except ParamValidationError as e:
            logger.warning(
                f"Parameter validation error for apply guardrail API: {str(e)}",
                extra={
                    "guardrail.identifier": guardrail_identifier,
                    "error.type": "ParamValidationError",
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=400,
                error_code="ValidationException",
                error_message=str(e),
                request_id="apply-guardrail-validation-error",
            ) from e
        except Exception as e:
            logger.error(
                f"Gateway error during apply guardrail API call: {str(e)}",
                extra={
                    "guardrail.identifier": guardrail_identifier,
                    "error.type": type(e).__name__,
                    "error.message": str(e),
                },
            )
            raise create_aws_http_exception(
                status_code=500,
                error_code="InternalServerError",
                error_message=f"Apply guardrail API failed: {str(e)}",
                request_id="apply-guardrail-gateway-error",
            ) from e

    return bedrock_router
