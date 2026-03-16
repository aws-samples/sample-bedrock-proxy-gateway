# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail middleware for processing guardrail configuration."""

import json
import logging
import re
from typing import Any

from fastapi import HTTPException, Request
from observability.context_logger import ContextLogger
from observability.context_vars import client_id_context
from observability.guardrail_metrics import (
    record_guardrail_applied,
    record_guardrail_not_found,
)
from observability.guardrail_tracing import guardrail_span
from services.guardrail_service import GuardrailService
from starlette.middleware.base import BaseHTTPMiddleware

logger = ContextLogger(logging.getLogger(__name__))


class GuardrailMiddleware(BaseHTTPMiddleware):
    """Middleware to handle guardrail configuration for Bedrock APIs."""

    def __init__(self, app, guardrail_service: GuardrailService):
        """Initialize guardrail middleware.

        Args:
        ----
            app: FastAPI application instance
            guardrail_service: Service for guardrail logical ID mapping
        """
        super().__init__(app)
        self.guardrail_service = guardrail_service

    async def dispatch(self, request: Request, call_next):
        """Process request and add guardrail configuration to request state."""
        # Only process Bedrock API endpoints
        if self._is_bedrock_endpoint(request.url.path):
            try:
                async with guardrail_span():
                    guardrail_config = await self._extract_guardrail_config(request)
                    request.state.guardrail_config = guardrail_config

            except HTTPException:
                # Re-raise HTTP exceptions (guardrail not found, etc.)
                raise
            except Exception as e:
                logger.error(f"Error processing guardrail config: {str(e)}")
                # Continue without guardrail config
                request.state.guardrail_config = None

        response = await call_next(request)
        return response

    def _is_bedrock_endpoint(self, path: str) -> bool:
        """Check if path is a Bedrock API endpoint."""
        bedrock_patterns = [
            r"/model/.+/converse",
            r"/model/.+/converse-stream",
            r"/model/.+/invoke",
            r"/model/.+/invoke-with-response-stream",
            r"/guardrail/.+/apply",
        ]
        return any(re.match(pattern, path) for pattern in bedrock_patterns)

    async def _extract_guardrail_config(self, request: Request) -> dict[str, Any] | None:
        """Extract guardrail configuration based on API type."""
        path = request.url.path
        client_id = client_id_context.get()

        # Extract shared account ID from rate limiting context
        shared_account_id = None
        if hasattr(request.state, "rate_ctx") and request.state.rate_ctx:
            try:
                # rate_ctx structure: (client_id, model_id, account_id, tpm, api_type)
                _, _, shared_account_id, _, _ = request.state.rate_ctx
            except (TypeError, ValueError):
                # rate_ctx is not a tuple or doesn't have enough elements
                shared_account_id = None

        if not shared_account_id:
            logger.warning("No shared account ID found in rate limiting context")
            return None

        # Header-based APIs (invoke, invoke-stream)
        if "/invoke" in path:
            return await self._get_guardrail_from_headers(request, shared_account_id, client_id)

        # Body-based APIs (converse, converse-stream)
        elif "/converse" in path:
            return await self._get_guardrail_from_body(request, shared_account_id, client_id)

        # Apply guardrail API
        elif "/guardrail/" in path and "/apply" in path:
            return await self._get_guardrail_from_path(request, shared_account_id)

        return None

    async def _get_guardrail_from_headers(
        self, request: Request, shared_account_id: str, client_id: str
    ) -> dict[str, Any] | None:
        """Get guardrail config from HTTP headers."""
        guardrail_logical_id = request.headers.get("X-Amzn-Bedrock-GuardrailIdentifier")

        if guardrail_logical_id and re.match("^[a-zA-Z0-9_-]+$", guardrail_logical_id):
            guardrail_config = await self.guardrail_service.get_guardrail_config(
                guardrail_logical_id, shared_account_id
            )
            if guardrail_config:
                logger.info(
                    f"Apply guardrail '{guardrail_logical_id}' for shared account '{shared_account_id}'"
                )
                # Record metrics
                record_guardrail_applied(
                    client_id, guardrail_logical_id, shared_account_id, "invoke"
                )

                if guardrail_config.get("trace"):
                    guardrail_config["trace"] = guardrail_config["trace"].upper()
                return guardrail_config
            else:
                # Record not found metrics
                record_guardrail_not_found(client_id, guardrail_logical_id, shared_account_id)

                raise HTTPException(
                    status_code=400,
                    detail=f"Guardrail '{guardrail_logical_id}' not found for account '{shared_account_id}'",
                )

        return None

    async def _get_guardrail_from_body(
        self, request: Request, shared_account_id: str, client_id: str
    ) -> dict[str, Any] | None:
        """Get guardrail config from request body."""
        try:
            # Read body without consuming it
            body_bytes = await request.body()
            if not body_bytes:
                return None

            body = json.loads(body_bytes.decode("utf-8"))

            # Check if user specified a logical guardrail ID in the request
            guardrail_identifier = body.get("guardrailConfig", {}).get("guardrailIdentifier")
            if guardrail_identifier and re.match("^[a-zA-Z0-9_-]+$", guardrail_identifier):
                guardrail_config = await self.guardrail_service.get_guardrail_config(
                    guardrail_identifier, shared_account_id
                )
                if guardrail_config:
                    logger.info(
                        f"Apply guardrail '{guardrail_identifier}' for shared account '{shared_account_id}'"
                    )
                    # Record metrics
                    record_guardrail_applied(
                        client_id, guardrail_identifier, shared_account_id, "converse"
                    )

                    # Store modified body for route to use
                    body["guardrailConfig"] = guardrail_config
                    request.state.modified_body = body
                    return guardrail_config
                else:
                    # Record not found metrics
                    record_guardrail_not_found(client_id, guardrail_identifier, shared_account_id)

                    raise HTTPException(
                        status_code=400,
                        detail=f"Guardrail '{guardrail_identifier}' not found for account '{shared_account_id}'",
                    )

        except json.JSONDecodeError:
            # Invalid JSON, let route handle it
            pass
        except Exception as e:
            logger.error(f"Error processing request body for guardrails: {str(e)}")

        return None

    async def _get_guardrail_from_path(
        self, request: Request, shared_account_id: str
    ) -> dict[str, Any] | None:
        """Get guardrail config from URL path for apply guardrail API."""
        # Extract guardrail identifier from path
        path_parts = request.url.path.split("/")
        try:
            guardrail_idx = path_parts.index("guardrail")
            if guardrail_idx + 1 < len(path_parts):
                guardrail_identifier = path_parts[guardrail_idx + 1]
                if re.match("^[a-zA-Z0-9_-]+$", guardrail_identifier):
                    guardrail_config = await self.guardrail_service.get_guardrail_config(
                        guardrail_identifier, shared_account_id
                    )
                    if guardrail_config:
                        logger.info(
                            f"Resolved logical guardrail ID '{guardrail_identifier}' to actual ID for shared account '{shared_account_id}'"
                        )
                        # Record metrics
                        record_guardrail_applied(
                            "unknown", guardrail_identifier, shared_account_id, "apply"
                        )

                        # Store resolved IDs for route to use
                        request.state.resolved_guardrail = {
                            "guardrailIdentifier": guardrail_config["guardrailIdentifier"],
                            "guardrailVersion": guardrail_config["guardrailVersion"],
                        }
                        return guardrail_config
                    else:
                        # Record not found metrics
                        record_guardrail_not_found(
                            "unknown", guardrail_identifier, shared_account_id
                        )

                        raise HTTPException(
                            status_code=400,
                            detail=f"Guardrail '{guardrail_identifier}' not found for account '{shared_account_id}'",
                        )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid guardrail logical ID '{guardrail_identifier}'",
                    )
        except (ValueError, IndexError):
            pass

        return None
