# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""FastAPI middleware for GenAI API rate limiting with O(1) performance.

This middleware implements comprehensive rate limiting for GenAI APIs with two key metrics:
1. RPM (Requests Per Minute): Limits number of API calls per client-model
2. TPM (Tokens Per Minute): Limits token consumption for cost control per client-model

KEY FEATURES:
- O(1) performance with Redis-backed counters and in-memory caching
- Shared rate limits across multiple AWS accounts per client
- CRI (Cross-Region Inference) model mapping for unified rate limiting
- Comprehensive observability with metrics, tracing, and structured logging
- Graceful fallbacks for Redis failures
- Standards-compliant HTTP 429 responses with proper headers

ARCHITECTURE:
- Middleware Layer: HTTP request interception and response handling
- Engine Layer: Business logic for quota management and account selection
- Limiter Layer: Redis-backed rate limiting with FixedWindow strategy
- Token Counter: Estimates and tracks token consumption across API types

REQUEST FLOW:
1. Extract model_id from URL path (/model/{model_id}/converse)
2. Skip rate limiting for public paths and non-model endpoints
3. Detect API type (converse, invoke) for token estimation
4. Estimate input tokens from request body
5. Resolve CRI model mapping for unified rate limiting
6. Check quota configuration with O(1) cache lookup
7. Select AWS account with available quota
8. Enforce RPM and TPM limits via Redis counters
9. Process request and add rate limit headers to response
10. Update actual token consumption from response

PERFORMANCE OPTIMIZATIONS:
- Pre-compiled regex for O(1) API type detection
- In-memory quota config caching (24h TTL)
- Minimal Redis operations (1-2 per request)
- Parallel account selection for unlimited quotas
- Atomic Redis operations for consistency
"""

import json
import logging
import time

from config import config
from core.rate_limit.engine import RateLimitEngine
from core.rate_limit.limiter import RateLimiter
from core.rate_limit.tokens import TokenCounter
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from observability.context_logger import ContextLogger
from observability.context_vars import client_id_context
from observability.rate_limit_metrics import (
    record_rate_limit_exceeded,
    record_rate_limit_request,
    record_redis_failure,
    record_tokens_consumed,
)
from observability.rate_limit_tracing import rate_limit_span
from starlette.middleware.base import BaseHTTPMiddleware
from util.constants import PUBLIC_PATHS, RATELIMIT_UNLIMITED

logger = ContextLogger(logging.getLogger(__name__))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for GenAI API rate limiting with comprehensive observability.

    CONFIGURATION:
    - JSON-based quota configuration with client permissions
    - CRI model mapping for unified rate limiting across regions
    - Environment-based enable/disable toggle
    """

    def _extract_model_id(self, path: str) -> str | None:
        """Extract model_id from URL path for rate limiting key generation.

        GenAI API endpoints follow the pattern: /model/{model_id}/{operation}
        This function extracts the model_id segment for use in rate limiting keys.

        Examples:
        - "/model/anthropic.claude-3-haiku/converse" → "anthropic.claude-3-haiku"
        - "/model/mistral.mistral-7b-instruct/invoke" → "mistral.mistral-7b-instruct"
        - "/health" → None (not a model endpoint)
        - "/model/" → None (missing model_id)

        RATE LIMITING KEYS:
        The extracted model_id is used to create Redis keys like:
        - "client123:anthropic.claude-3-haiku:rpm" (requests per minute)
        - "client123:anthropic.claude-3-haiku:tpm" (tokens per minute)

        Args:
        ----
            path: HTTP request path from request.url.path

        Returns:
        -------
            Model identifier string or None if not a valid model endpoint
        """
        if not path.startswith("/model/"):
            return None

        # Split and validate path structure: ['', 'model', 'model_id', ...]
        parts = path.split("/")
        if len(parts) < 3 or parts[1] != "model":
            return None

        return parts[2] if parts[2] else None

    def _is_guardrail_endpoint(self, path: str) -> bool:
        """Check if path is a guardrail endpoint.

        Guardrail endpoints follow the pattern:
        /guardrail/{guardrailIdentifier}/version/{guardrailVersion}/apply
        """
        import re

        return bool(re.match(r"^/guardrail/[^/]+/version/[^/]+/apply$", path))

    def _set_account_for_bypass(self, request: Request, is_guardrail: bool, model_id: str | None):
        """Set account for requests that bypass rate limiting."""
        if not self.rate_config or not (model_id or is_guardrail):
            return

        try:
            if is_guardrail:
                client_accounts = self._get_client_accounts()
            else:
                client_accounts = self._get_default_accounts()

            if client_accounts:
                import secrets

                selected_account_id = secrets.choice(client_accounts)
                endpoint_type = "guardrail" if is_guardrail else model_id
                request.state.rate_ctx = (None, endpoint_type, selected_account_id, None, None)

                logger.debug(
                    f"Set {'client' if is_guardrail else 'default'} account",
                    extra={
                        "event.name": "rate_limit_guardrail_account"
                        if is_guardrail
                        else "rate_limit_default_account",
                        "cloud.account.id": selected_account_id,
                        "gen_ai.request.model": model_id,
                    },
                )
        except Exception as e:
            logger.error(
                f"Failed to set account for {'guardrail' if is_guardrail else 'rate limiting'}",
                extra={"event.name": "rate_limit_account_error", "error.message": str(e)},
            )

    def _get_client_accounts(self) -> list[str]:
        """Get client-specific accounts, fallback to default if none found."""
        client_id = client_id_context.get()
        if client_id:
            client_accounts = (
                self.rate_config.get("permissions", {}).get(client_id, {}).get("accounts", [])
            )
            if client_accounts:
                return client_accounts
        return self._get_default_accounts()

    def _get_default_accounts(self) -> list[str]:
        """Get default accounts from configuration."""
        return self.rate_config.get("permissions", {}).get("default", {}).get("accounts", [])

    def _set_client_name_context(self, client_id: str):
        """Set client name in context for logging."""
        if not self.rate_config or "permissions" not in self.rate_config:
            return

        client_permissions = self.rate_config["permissions"].get(client_id, {})
        client_name = client_permissions.get("name")

        if client_name:
            from observability.context_vars import client_name_context

            client_name_context.set(client_name)

    def __init__(self, app):
        """Initialize rate limiting middleware with configuration validation.

        - Validates config and enables/disables rate limiting
        - Sets up Redis limiter, token counter, CRI resolver
        - Creates rate limiting engine with quota management
        - Fails gracefully on invalid config

        Args:
        ----
            app: FastAPI application instance
        """
        super().__init__(app)
        self.enabled = config.rate_limiting_enabled
        self.rate_config = None

        # Always load rate config for default account lookup
        try:
            if config.rate_limit_config:
                self.rate_config = json.loads(config.rate_limit_config)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(
                "Failed to load rate limit config for default account",
                extra={"event.name": "rate_limit_config_warning", "error.message": str(e)},
            )

        if not self.enabled:
            return

        try:
            limiter = RateLimiter()
            self.tokens = TokenCounter()

            if not self.rate_config or not isinstance(self.rate_config.get("permissions"), dict):
                raise ValueError("Invalid rate limit config: missing permissions")

            self.rate_limiter = RateLimitEngine(limiter, self.rate_config)

        except Exception as e:
            logger.error(
                "Rate limiting disabled due to configuration error",
                extra={"event.name": "rate_limit_config_error", "error.message": str(e)},
            )
            self.enabled = False

    async def dispatch(self, request: Request, call_next):
        """Process HTTP requests through rate limiting middleware.

        This is the core middleware function that intercepts every HTTP request
        and applies rate limiting logic before passing to the next middleware/handler.

        Args:
        ----
            request: FastAPI Request object with URL, headers, body
            call_next: Next middleware/handler in the chain

        Returns:
        -------
            HTTP response with rate limit headers added

        Raises:
        ------
            HTTPException: 429 if rate limit exceeded, 403 if no quota configured
        """
        # STEP 1: Extract model_id from URL path since middleware runs before route matching
        # This is needed because FastAPI middleware executes before route resolution,
        # so we must parse the URL manually to identify model endpoints
        model_id = self._extract_model_id(request.url.path)

        if request.url.path not in PUBLIC_PATHS:
            logger.debug(
                "Rate limit middleware entry",
                extra={
                    "event.name": "rate_limit_entry",
                    "url.path": request.url.path,
                    "gen_ai.request.model": model_id,
                    "rate_limiting_enabled": self.enabled,
                },
            )

        # STEP 2: Early exit conditions and account assignment
        # Handle guardrail endpoints and other non-rate-limited requests
        is_guardrail = self._is_guardrail_endpoint(request.url.path)
        should_skip_rate_limiting = (
            not self.enabled
            or request.url.path in PUBLIC_PATHS
            or (not model_id and not is_guardrail)
        )

        if is_guardrail or should_skip_rate_limiting:
            # Set account_id when needed and config is available
            self._set_account_for_bypass(request, is_guardrail, model_id)

            if request.url.path not in PUBLIC_PATHS and not is_guardrail:
                logger.debug(
                    "Rate limiting skipped",
                    extra={
                        "event.name": "rate_limit_skipped",
                        "reason": "disabled" if not self.enabled else "no_model_id",
                    },
                )
            return await call_next(request)

        try:
            # STEP 3: Rate limiting logic within its own span with duration tracking
            rate_limit_start = time.time()
            cache_start = None
            async with rate_limit_span():
                # Get client identifier from request context
                # This is set by the authentication middleware that runs before rate limiting
                # Used as the primary key for rate limiting: "client_id:model_id:metric"
                client_id = client_id_context.get()

                logger.debug(
                    "Rate limit processing",
                    extra={
                        "event.name": "rate_limit_processing",
                        "gen_ai.request.model": model_id,
                        "url.path": request.url.path,
                    },
                )

                # STEP 4: O(1) API type detection using pre-compiled regex patterns
                # Maps URL patterns to API types for token estimation:
                # - "/model/.../converse" → "converse" (chat API)
                # - "/model/.../invoke" → "invoke" (legacy API)
                api_type = self.rate_limiter.get_api_type(request.url.path)
                if not api_type:
                    logger.info(
                        "No API type detected, skipping rate limit",
                        extra={
                            "event.name": "rate_limit_no_api_type",
                            "url.path": request.url.path,
                        },
                    )

                    return await call_next(request)

                # STEP 5: Token estimation
                # Parse request body to estimate input token consumption
                request_body = await request.json()
                estimated_tokens = self.tokens.estimate(request_body, api_type)

                # STEP 6: O(1) quota configuration lookup with 24h in-memory caching
                # Retrieves RPM/TPM limits and available AWS accounts for this client-model
                # Cache hit: sub-microsecond lookup, Cache miss: JSON parsing + validation
                try:
                    quota_config = await self.rate_limiter.get_quota_config(client_id, model_id)

                    # Extract and set client name from rate limit config for logging
                    self._set_client_name_context(client_id)

                except HTTPException as e:
                    if 400 <= e.status_code < 500:
                        # Handle all 4xx client errors with proper JSON response
                        logger.warning(
                            "Rate limit client error",
                            extra={
                                "event.name": "rate_limit_client_error",
                                "gen_ai.request.model": model_id,
                                "http.response.status_code": e.status_code,
                                "error.message": e.detail,
                            },
                        )
                        from util.aws_error_response import create_aws_error_response

                        return create_aws_error_response(
                            status_code=e.status_code,
                            error_code="AccessDenied" if e.status_code == 403 else "BadRequest",
                            error_message=e.detail,
                            request_id="rate-limit-error",
                        )
                    raise

                # STEP 7: AWS account selection with quota enforcement
                # For unlimited quotas: Round-robin load balancing
                # For limited quotas: Check Redis counters and select available account
                # Returns tuple with account_id, reason, scope, and usage metrics
                cache_start = time.time()
                (
                    account_id,
                    reason,
                    scope,
                    rpm_used,
                    tpm_used,
                ) = await self.rate_limiter.select_account(
                    client_id, model_id, quota_config, estimated_tokens
                )
                cache_duration = (time.time() - cache_start) * 1000 if cache_start else None

                # Store usage for response headers
                request.state.rpm_used = rpm_used
                request.state.tpm_used = tpm_used

                logger.debug(
                    "Rate limit account selection",
                    extra={
                        "event.name": "rate_limit_account_selection",
                        "cloud.account.id": account_id,
                        "gen_ai.request.model": model_id,
                        "rate_limit.rpm_used": rpm_used,
                        "rate_limit.tpm_used": tpm_used,
                    },
                )
                # STEP 8: Handle rate limit exceeded (account_id = None)
                if not account_id:
                    # Record metrics for monitoring and alerting
                    record_rate_limit_exceeded(
                        client_id, model_id, reason.value if reason else "unknown"
                    )
                    record_rate_limit_request(client_id, model_id, "none", "exceeded")

                    # Log performance data for Athena analysis
                    logger.info(
                        "Rate limit performance",
                        extra={
                            "event.name": "rate_limit_performance",
                            "gen_ai.request.model": model_id,
                            "client.address": request.client.host if request.client else "unknown",
                            "http.request.method": request.method,
                            "url.path": request.url.path,
                            "rate_limit.duration_ms": round(
                                (time.time() - rate_limit_start) * 1000, 3
                            ),
                            "rate_limit.redis_duration_ms": round(cache_duration, 3)
                            if cache_duration
                            else None,
                            "rate_limit.result": "exceeded",
                            "rate_limit.reason": reason.value if reason else None,
                            "rate_limit.scope": scope.value if scope else None,
                            "rate_limit.rpm_used": rpm_used,
                            "rate_limit.tpm_used": tpm_used,
                            "cloud.account.id": "none",
                        },
                    )

                    logger.warning(
                        "Rate limit exceeded",
                        extra={
                            "event.name": "rate_limit_exceeded",
                            "gen_ai.request.model": model_id,
                            "rate_limit.rpm": quota_config.rpm,
                            "rate_limit.tpm": quota_config.tpm,
                            "rate_limit.rpm_used": rpm_used,
                            "rate_limit.tpm_used": tpm_used,
                            "rate_limit.reason": reason.value if reason else None,
                            "rate_limit.scope": scope.value if scope else None,
                            "gen_ai.usage.input_tokens": estimated_tokens,
                        },
                    )

                    # Return HTTP 429 with standards-compliant rate limit headers
                    # Headers include: X-RateLimit-Limit, X-RateLimit-Reset, Retry-After
                    # Plus X-RateLimit-Reason and X-RateLimit-Scope for debugging
                    # Using JSONResponse instead of HTTPException for better header control
                    error = self.rate_limiter.create_rate_limit_error(quota_config, reason, scope)
                    from util.aws_error_response import create_aws_error_response

                    return create_aws_error_response(
                        status_code=error.status_code,
                        error_code="ThrottlingException",
                        error_message=error.detail,
                        request_id="rate-limit-exceeded",
                        headers=error.headers,
                    )

                # STEP 9: Record successful rate limit check
                # Distinguish between unlimited quotas (no Redis checks) and limited quotas
                status = "unlimited" if quota_config.is_unlimited else "allowed"
                record_rate_limit_request(client_id, model_id, account_id, status)

                # Log performance data for Athena analysis
                logger.info(
                    "Rate limit performance",
                    extra={
                        "event.name": "rate_limit_performance",
                        "gen_ai.request.model": model_id,
                        "client.address": request.client.host if request.client else "unknown",
                        "http.request.method": request.method,
                        "url.path": request.url.path,
                        "rate_limit.duration_ms": round(
                            (time.time() - rate_limit_start) * 1000, 3
                        ),
                        "rate_limit.redis_duration_ms": round(cache_duration, 3)
                        if cache_duration
                        else None,
                        "rate_limit.result": status,
                        "cloud.account.id": account_id,
                    },
                )

                logger.debug(
                    f"Rate limit check passed {status}",
                    extra={
                        "event.name": "rate_limit_passed",
                        "gen_ai.request.model": model_id,
                        "cloud.account.id": account_id,
                        "gen_ai.usage.input_tokens": estimated_tokens,
                    },
                )

                # STEP 10: Store rate limiting context for post-processing
                # This context is used later to update actual token consumption
                # and add rate limit headers to the response
                request.state.rate_ctx = (
                    client_id,
                    model_id,
                    account_id,
                    quota_config.tpm,
                    api_type,
                )

            # STEP 11: Process request through remaining middleware and handlers
            # At this point, rate limits have been checked and account selected
            # This call is outside the rate_limit_span so model calls get their own spans
            response = await call_next(request)

            # STEP 12: Add rate limit headers to response for client guidance
            # Headers inform clients about their current usage and reset times
            if hasattr(request.state, "rate_ctx"):
                client_id, model_id, _, _, _ = request.state.rate_ctx
                rpm_used = getattr(request.state, "rpm_used", 0)
                tpm_used = getattr(request.state, "tpm_used", 0)
                await self._add_rate_limit_headers(
                    response, model_id, quota_config, rpm_used, tpm_used
                )

                # STEP 13: Update actual token consumption from response body
                # Replace estimated tokens with actual tokens from model response
                # This ensures accurate TPM tracking for cost control
                await self._update_tokens(request, response)

            return response

        except HTTPException:
            # STEP 14: Handle HTTP exceptions (rate limit exceeded, config errors)
            # These are already handled above with proper duration recording
            raise
        except Exception:
            # STEP 15: Handle unexpected exceptions
            # Record error metrics for rate limiting failures

            raise

    async def _add_rate_limit_headers(
        self, response, model_id: str, quota_config, rpm_used: int, tpm_used: int
    ):
        """Add standards-compliant rate limit headers to HTTP response.

        Adds informational headers to help clients understand their rate limit status
        and when they can make additional requests. These headers follow HTTP standards
        and best practices for rate limiting APIs.

        HEADERS ADDED:
        - x-ratelimit-limit-rpm: Maximum requests per minute allowed
        - x-ratelimit-limit-tpm: Maximum tokens per minute allowed
        - x-ratelimit-used-rpm: Current requests used in this minute
        - x-ratelimit-used-tpm: Current tokens used in this minute
        - x-ratelimit-reset-rpm: Unix timestamp when RPM counter resets
        - x-ratelimit-reset-tpm: Unix timestamp when TPM counter resets

        RESET TIME CALCULATION:
        - Uses FixedWindow strategy: resets at minute boundaries (e.g., 10:30:00, 10:31:00)
        - Provides predictable reset times for client retry logic
        - Graceful fallback if Redis fails to provide reset time

        Args:
        ----
            response: FastAPI Response object to add headers to
            model_id: Model identifier for logging
            quota_config: QuotaConfig with RPM/TPM limits
            rpm_used: Current RPM usage
            tpm_used: Current TPM usage
        """
        try:
            # Get next window reset time from FixedWindow rate limiter
            # This calculates when the current minute window ends and counters reset
            reset_time = self.rate_limiter.limiter.get_reset_time()

            # Set rate limit headers (lowercase for HTTP standard compliance)
            # These headers inform clients about their quota limits and reset times
            response.headers["x-ratelimit-limit-rpm"] = str(quota_config.rpm)
            response.headers["x-ratelimit-limit-tpm"] = str(quota_config.tpm)
            response.headers["x-ratelimit-used-rpm"] = str(rpm_used)
            response.headers["x-ratelimit-used-tpm"] = str(tpm_used)
            response.headers["x-ratelimit-reset-rpm"] = str(reset_time)
            response.headers["x-ratelimit-reset-tpm"] = str(reset_time)

        except Exception as e:
            logger.error(
                "Failed to add rate limit headers",
                extra={
                    "event.name": "rate_limit_headers_error",
                    "gen_ai.request.model": model_id,
                    "error.message": str(e),
                },
            )

    async def _update_tokens(self, request: Request, response):
        """Update Redis TPM counters with actual token consumption from model response.

        This function replaces estimated input tokens with actual tokens consumed
        by the model, ensuring accurate TPM tracking for cost control.

        TOKEN TRACKING FLOW:
        1. Initial request: Estimate input tokens for rate limit check
        2. Model processing: Actual tokens consumed (input + output)
        3. Response processing: Update Redis with actual token count

        WHY THIS MATTERS:
        - Token estimation is approximate (based on character count)
        - Actual tokens depend on model tokenization and response length
        - Accurate tracking prevents quota abuse and ensures fair billing

        REDIS OPERATIONS:
        - Updates shared TPM counter: "client:model:tpm"
        - Only updates if TPM is limited (not unlimited)
        - Uses atomic operations to prevent race conditions

        SUPPORTED RESPONSE TYPES:
        - JSON responses: Parse usage.total_tokens from response body
        - Todo: Streaming responses: Skip (tokens tracked differently)
        - Error responses: Skip (no tokens consumed)

        Args:
        ----
            request: FastAPI Request with rate_ctx stored in state
            response: FastAPI Response with token usage in body
        """
        try:
            # STEP 1: Skip token updates for streaming or empty responses
            # Streaming responses handle token tracking differently
            # Empty responses indicate errors or non-model endpoints
            if isinstance(response, StreamingResponse) or not (
                hasattr(response, "body") and response.body
            ):
                return

            # STEP 2: Extract rate limiting context and parse response
            # Context was stored during initial rate limit check
            client_id, model_id, account_id, tpm_limit, api_type = request.state.rate_ctx
            response_data = json.loads(response.body.decode("utf-8"))

            # STEP 3: Extract aggregated tokens using model-specific calculation
            actual_tokens = self.tokens.extract(response_data, api_type, model_id)

            # STEP 4: Update shared TPM counter with actual tokens
            # TPM limits are shared across all AWS accounts for this client-model
            # Only update Redis if TPM is limited (not unlimited)
            if tpm_limit != RATELIMIT_UNLIMITED:
                shared_tpm_key = f"{client_id}:{model_id}:tpm"
                await self.rate_limiter.limiter.check_and_consume(
                    shared_tpm_key, tpm_limit, actual_tokens
                )

            # STEP 5: Record token consumption metrics for monitoring
            record_tokens_consumed(client_id, model_id, actual_tokens, api_type)

            logger.debug(
                "Token count updated",
                extra={
                    "event.name": "token_update",
                    "gen_ai.request.model": model_id,
                    "cloud.account.id": account_id,
                    "gen_ai.usage.output_tokens": actual_tokens,
                    "gen_ai.operation.name": api_type,
                },
            )
        except Exception as e:
            # GRACEFUL FALLBACK: Log Redis failures but don't block requests
            # Token updates are important for accuracy but not critical for functionality
            if "redis" in str(e).lower():
                record_redis_failure("token_update", type(e).__name__)
                logger.error(
                    "Redis failure during token update",
                    extra={
                        "event.name": "redis_failure_token_update",
                        "gen_ai.request.model": request.state.rate_ctx[1],
                        "error.message": str(e),
                    },
                )
