# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Rate limiting engine with O(1) performance.

This module implements the business logic layer for rate limiting in GenAI APIs.
It sits between the middleware (HTTP layer) and limiter (Redis layer), handling:

1. Quota configuration management and caching
2. Account selection logic for load balancing
3. API endpoint pattern matching
4. Rate limit error generation

KEY ARCHITECTURAL DECISIONS:
- Shared limits across multiple AWS accounts per client (not per-account limits)
- In-memory caching for sub-millisecond quota lookups
- Round-robin load balancing for unlimited quotas
- Graceful fallbacks for Redis failures
- Immutable configuration objects for thread safety

PERFORMANCE CHARACTERISTICS:
- O(1) quota lookups via memory cache
- O(1) API type detection via pre-compiled regex
- Minimal Redis operations (1-2 per request)
- Sub-millisecond response times for cached configurations
"""

import re
import time
from dataclasses import dataclass
from typing import Final

from core.cache.memory_cache import get_cache, set_cache
from fastapi import HTTPException
from observability.rate_limit_metrics import record_redis_failure
from util.constants import RATELIMIT_UNLIMITED
from util.rate_limit_types import RateLimitReason, RateLimitScope

# API endpoint patterns for O(1) lookup - Pre-compiled regex for performance
# Maps URL patterns to API types for token estimation and metrics
API_PATTERNS: Final[dict[re.Pattern, str]] = {
    re.compile(r"/model/[^/]+/converse$"): "converse",  # Standard chat API
    re.compile(r"/model/[^/]+/converse-stream$"): "converse",  # Streaming chat API
    re.compile(r"/model/[^/]+/invoke$"): "invoke",  # Legacy invoke API
    re.compile(r"/model/[^/]+/invoke-with-response-stream$"): "invoke",  # Legacy streaming API
}

# Rate limiting constants
UNLIMITED: Final[int] = RATELIMIT_UNLIMITED  # Alias for backward compatibility
DEFAULT_RESET: Final[int] = 60  # Default reset time for error headers (seconds)
RR_EXPIRY: Final[int] = 3600  # Round-robin counter expiry (1 hour)
QUOTA_CACHE_EXPIRY: Final[int] = 86400  # Quota config cache expiry (24 hours)


@dataclass(frozen=True)
class QuotaConfig:
    """Immutable quota configuration for a client-model combination.

    This dataclass encapsulates all rate limiting parameters for a specific
    client using a specific model. The frozen=True ensures immutability
    for thread safety and caching reliability.

    Example:
    QuotaConfig(rpm=100, tpm=10000, accounts=["123456789", "987654321"])
    → Client can make 100 requests/min, consume 10K tokens/min across 2 AWS accounts
    """

    rpm: int  # Requests per minute limit (-1 for unlimited)
    tpm: int  # Tokens per minute limit (-1 for unlimited)
    accounts: list[str]  # AWS account IDs available for this client-model

    @property
    def is_unlimited(self) -> bool:
        """Check if both RPM and TPM are unlimited.

        Used for optimization - unlimited quotas skip Redis checks entirely
        and use simple round-robin account selection.

        Returns
        -------
            True if both RPM and TPM are -1 (unlimited)
        """
        return self.rpm == UNLIMITED and self.tpm == UNLIMITED


class RateLimitEngine:
    """Core rate limiting engine with O(1) performance.

    This is the main business logic component that orchestrates rate limiting.
    It handles quota lookups, account selection, and integrates with the Redis
    limiter for actual rate limit enforcement.

    ARCHITECTURE:
    - Caches quota configurations in memory for sub-millisecond lookups
    - Enforces shared limits across multiple AWS accounts per client
    - Uses round-robin load balancing for unlimited quotas
    - Provides fallback mechanisms for Redis failures
    """

    def __init__(self, limiter, rate_config: dict):
        """Initialize rate limiting engine.

        Args:
        ----
            limiter: RateLimiter instance for Redis operations
            rate_config: Configuration dict with permissions and account_limits
        """
        self.limiter = limiter
        self.permissions = rate_config.get("permissions", {})
        self.account_limits = rate_config.get("account_limits", {})

    @staticmethod
    def get_api_type(url_path: str) -> str | None:
        """Detect API type from URL path using pre-compiled regex patterns.

        This function maps incoming request URLs to API types for:
        1. Token estimation (different APIs have different token patterns)
        2. Metrics categorization
        3. Rate limiting logic

        Examples:
        - "/model/claude-3-haiku/converse" → "converse"
        - "/model/mistral/invoke" → "invoke"
        - "/health" → None (not a model API)

        Args:
        ----
            url_path: HTTP request path (e.g., "/model/claude-3-haiku/converse")

        Returns:
        -------
            API type string or None if no pattern matches
        """
        # O(1) lookup using pre-compiled regex patterns
        for pattern, api_type in API_PATTERNS.items():
            if pattern.search(url_path):
                return api_type
        return None  # Not a recognized model API endpoint

    async def get_quota_config(self, client_id: str, model_id: str) -> QuotaConfig:
        """Get cached quota configuration with ultra-fast lookup.

        This is a critical performance path that must be sub-millisecond.
        Uses in-memory caching to avoid repeated JSON parsing and validation.

        CACHE STRATEGY:
        1. Check memory cache first (sub-microsecond)
        2. If miss, parse config and validate
        3. Cache result for 24 hours
        4. Return immutable QuotaConfig object

        FALLBACK LOGIC:
        - If client_id not found, try "default" configuration
        - Validates all required fields exist
        - Raises appropriate HTTP exceptions for missing/invalid config

        Args:
        ----
            client_id: Client identifier (for example, "EXAMPLECLIENTID123456789ABCDEF")
            model_id: Model identifier (e.g., "anthropic.claude-3-haiku-20240307-v1:0")

        Returns:
        -------
            QuotaConfig object with RPM, TPM limits and available accounts

        Raises:
        ------
            HTTPException: 403 if no quota configured, 500 if config invalid
        """
        cache_key = f"quota:{client_id}:{model_id}"

        # STEP 1: Try cache first (sub-microsecond lookup)
        cached_config = await get_cache(cache_key)
        if cached_config:
            return cached_config  # Cache hit - return immediately

        # STEP 2: Cache miss - compute configuration
        # Try specific client first, fallback to "default" if not found
        client_config = self.permissions.get(client_id) or self.permissions.get("default")
        if not client_config:
            raise HTTPException(403, "No quota configured")

        # STEP 3: Extract model-specific quotas
        quotas = client_config.get("models", {}).get(model_id)
        if not quotas or not client_config.get("accounts"):
            raise HTTPException(403, f"No quota configured for model {model_id}")

        # STEP 4: Validate required fields
        if not all(key in quotas for key in ["rpm", "tpm"]):
            raise HTTPException(500, "Invalid quota configuration")

        # STEP 5: Create immutable config object
        config = QuotaConfig(quotas["rpm"], quotas["tpm"], client_config["accounts"])

        # STEP 6: Cache for 24 hours to avoid repeated parsing
        await set_cache(cache_key, config, QUOTA_CACHE_EXPIRY)
        return config

    async def select_account(
        self, client_id: str, model_id: str, quota_config: QuotaConfig, tokens: int
    ) -> tuple[str | None, RateLimitReason | None, RateLimitScope | None, int, int]:
        """Select AWS account with available quota for this request.

        This function implements the core account selection logic:
        1. For unlimited quotas: Use hash-based selection for load balancing
        2. For limited quotas: Check Redis counters and select available account

        ACCOUNT SELECTION STRATEGY:
        - Multiple AWS accounts per client for horizontal scaling
        - Shared rate limits across all accounts (not per-account limits)
        - Load balancing to distribute requests evenly

        Args:
        ----
            client_id: Client identifier
            model_id: Model identifier
            quota_config: Quota configuration with limits and accounts
            tokens: Number of tokens this request will consume

        Returns:
        -------
            Tuple of (account_id, reason, scope, rpm_used, tpm_used):
            - account_id: AWS account ID to use, or None if rate limited
            - reason: Rate limit reason if exceeded, None otherwise
            - scope: Rate limit scope if exceeded, None otherwise
            - rpm_used: Current RPM usage
            - tpm_used: Current TPM usage
        """
        # Fast path: Unlimited quotas skip Redis entirely
        if quota_config.is_unlimited:
            account = await self._hash_based_account(client_id, model_id, quota_config.accounts)
            return (account, None, None, 0, 0)

        # Limited quotas: Check Redis counters for available capacity
        return await self._find_available_account(client_id, model_id, quota_config, tokens)

    async def _find_available_account(
        self, client_id: str, model_id: str, quota_config: QuotaConfig, tokens: int
    ) -> tuple[str | None, RateLimitReason | None, RateLimitScope | None, int, int]:
        """Find account with sufficient quota, enforcing both client and account limits.

        DUAL-LEVEL LIMITS ARCHITECTURE:
        - Client limits: Shared across ALL accounts for a client-model combination
        - Account limits: Per-account limits to prevent exceeding AWS quotas

        REDIS KEY STRUCTURE:
        - Client TPM: "client1:claude-3-haiku:tpm" → shared token counter
        - Client RPM: "client1:claude-3-haiku:rpm" → shared request counter
        - Account TPM: "123456789012:claude-3-haiku:tpm" → account token counter
        - Account RPM: "123456789012:claude-3-haiku:rpm" → account request counter

        SINGLE REDIS CALL:
        All 4 limits checked atomically in one Lua script execution

        QUOTA MONITORING:
        - Captures rpm_used and tpm_used from check_and_consume_all
        - Returns usage even when rate limit exceeded for alerting

        Args:
        ----
            client_id: Client identifier
            model_id: Model identifier
            quota_config: Quota limits and available accounts
            tokens: Estimated tokens for this request

        Returns:
        -------
            Tuple of (account_id, reason, scope, rpm_used, tpm_used):
            - account_id: Account ID if quota available, None if rate limited
            - reason: Rate limit reason if exceeded, None otherwise
            - scope: Rate limit scope if exceeded, None otherwise
            - rpm_used: Current RPM usage
            - tpm_used: Current TPM usage
        """
        rpm_used = 0
        tpm_used = 0

        try:
            # Check all limits in single Redis call
            shared_rpm_key = f"{client_id}:{model_id}:rpm"
            shared_tpm_key = f"{client_id}:{model_id}:tpm"

            # Get account limits
            account_id = quota_config.accounts[0] if quota_config.accounts else None
            if not account_id:
                return (None, None, None, 0, 0)

            account_config = self.account_limits.get(account_id, {}).get(model_id, {})
            account_rpm_key = f"{account_id}:{model_id}:rpm"
            account_tpm_key = f"{account_id}:{model_id}:tpm"
            account_rpm_limit = account_config.get("rpm", RATELIMIT_UNLIMITED)
            account_tpm_limit = account_config.get("tpm", RATELIMIT_UNLIMITED)

            success, rpm_used, tpm_used, reason, scope = await self.limiter.check_and_consume_all(
                shared_rpm_key,
                quota_config.rpm,
                shared_tpm_key,
                quota_config.tpm,
                account_rpm_key,
                account_rpm_limit,
                account_tpm_key,
                account_tpm_limit,
                tokens,
            )

            if not success:
                limit_reason = RateLimitReason.RPM if reason == "rpm" else RateLimitReason.TPM
                if scope == "account":
                    limit_reason = (
                        RateLimitReason.ACCOUNT_RPM
                        if reason == "rpm"
                        else RateLimitReason.ACCOUNT_TPM
                    )
                limit_scope = (
                    RateLimitScope.CLIENT if scope == "client" else RateLimitScope.ACCOUNT
                )
                return (None, limit_reason, limit_scope, rpm_used, tpm_used)

            return (account_id, None, None, rpm_used, tpm_used)

        except Exception as e:
            # FALLBACK: If Redis fails, allow request but log the failure
            record_redis_failure("quota_check", type(e).__name__)
            account = await self._hash_based_account(client_id, model_id, quota_config.accounts)
            return (account, None, None, 0, 0)

    async def _hash_based_account(self, client_id: str, model_id: str, accounts: list[str]) -> str:
        """Hash-based account selection for unlimited quotas.

        Uses deterministic hashing to distribute load evenly across AWS accounts
        without Redis overhead. Each client-model gets consistent distribution.

        ALGORITHM:
        1. Hash client_id + model_id + current timestamp (seconds)
        2. Use modulo to select account index
        3. Provides even distribution across all processes

        Benefits:
        - Zero Redis calls for unlimited quotas
        - Deterministic distribution per client-model

        Args:
        ----
            client_id: Client identifier
            model_id: Model identifier
            accounts: List of available AWS account IDs

        Returns:
        -------
            Selected AWS account ID for load balancing
        """
        import hashlib
        import time

        # Create hash from client, model, and current second
        # This ensures distribution changes every second
        hash_input = f"{client_id}:{model_id}:{int(time.time())}"
        hash_value = int(hashlib.md5(hash_input.encode(), usedforsecurity=False).hexdigest(), 16)

        # Select account using modulo
        selected_index = hash_value % len(accounts)
        return accounts[selected_index]

    def create_rate_limit_error(
        self,
        quota_config: QuotaConfig,
        reason: RateLimitReason | None = None,
        scope: RateLimitScope | None = None,
    ) -> HTTPException:
        """Create HTTP 429 error with proper rate limit headers.

        Generates a standards-compliant rate limit error response with headers
        that inform clients when they can retry their requests.

        HEADERS INCLUDED:
        - X-RateLimit-Limit: The rate limit ceiling for this client
        - X-RateLimit-Remaining: Always "0" since limit was exceeded
        - X-RateLimit-Reset: Unix timestamp when the limit resets
        - Retry-After: Seconds to wait before retrying
        - X-RateLimit-Reason: Which limit was exceeded (rpm, tpm, account_rpm, account_tpm)
        - X-RateLimit-Scope: Which scope was exceeded (client, account)

        FALLBACK BEHAVIOR:
        - If Redis fails to provide reset time, use current time + 60 seconds
        - This ensures clients always get a reasonable retry time

        Args:
        ----
            quota_config: Quota configuration with RPM/TPM limits
            reason: Rate limit reason (rpm, tpm, account_rpm, account_tpm)
            scope: Rate limit scope (client, account)

        Returns:
        -------
            HTTPException with 429 status and rate limit headers
        """
        try:
            # Get actual reset time from Redis (next minute boundary)
            reset_time = str(self.limiter.get_reset_time())
        except Exception:
            # FALLBACK: If Redis fails, estimate reset time
            reset_time = str(int(time.time()) + DEFAULT_RESET)

        # Standard rate limit headers for client guidance
        headers = {
            "X-RateLimit-Limit": str(quota_config.rpm),  # Show RPM limit (more user-friendly)
            "X-RateLimit-Remaining": "0",  # Always 0 when limit exceeded
            "X-RateLimit-Reset": reset_time,  # When limit resets (Unix timestamp)
            "Retry-After": str(DEFAULT_RESET),  # Seconds to wait (for HTTP standard)
        }

        # Add reason and scope headers for debugging
        if reason:
            headers["X-RateLimit-Reason"] = reason.value
        if scope:
            headers["X-RateLimit-Scope"] = scope.value

        return HTTPException(429, "Rate limit exceeded", headers=headers)
