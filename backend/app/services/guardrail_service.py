"""Guardrail service for managing logical ID to actual ID mapping.

This service provides O(1) guardrail configuration lookups using Redis caching
with automatic refresh from SSM Parameter Store.

KEY FEATURES:
- Redis-backed shared cache across all ECS tasks
- Periodic SSM refresh (configurable interval)
- Graceful fallback to SSM on Redis failures
- Sub-millisecond lookups for latency-sensitive operations

ARCHITECTURE:
- Primary cache: Redis (shared, 1-2ms latency)
- Fallback: Direct SSM read (50-100ms latency)
- Background refresh: Periodic SSM check and Redis update
"""

import asyncio
import json
import logging
import time

from config import config
from observability.context_logger import ContextLogger
from util.ssm_client import SSMClient

logger = ContextLogger(logging.getLogger(__name__))


class GuardrailService:
    """Service for managing guardrail logical ID mappings with Redis caching.

    CACHING STRATEGY:
    1. All requests read from Redis (fast, shared across tasks)
    2. Background thread refreshes from SSM every N minutes
    3. On Redis failure, fallback to direct SSM read
    4. Redis TTL is 2x refresh interval for safety
    """

    def __init__(self):
        """Initialize guardrail service with lazy Valkey initialization."""
        self._ssm_client = SSMClient()
        self._redis = None
        self._last_refresh = 0
        self._refresh_interval = config.guardrail_refresh_interval
        self._redis_ttl = int(self._refresh_interval * 2)  # 10 min
        self._redis_key = f"guardrails:{config.environment}:consolidated-config"
        self._ssm_parameter = (
            f"bedrock-gateway/{config.environment}/guardrails/consolidated-config"
        )
        self._refresh_lock = asyncio.Lock()

    async def _ensure_redis(self):
        """Ensure Valkey client is initialized."""
        if self._redis is None:
            try:
                from services.valkey_service import create_valkey_client

                self._redis = await create_valkey_client()
            except Exception as e:
                logger.warning(
                    f"Valkey initialization failed, using SSM fallback: {e}",
                    extra={"event.name": "guardrail_valkey_init_failed", "error.message": str(e)},
                )

    async def _ensure_config_fresh(self) -> None:
        """Ensure guardrail config in Valkey is fresh by periodic SSM refresh.

        REFRESH LOGIC:
        1. Check if refresh interval elapsed
        2. If yes, acquire lock and load from SSM
        3. Update Valkey with new config
        4. All ECS tasks benefit from shared Valkey cache

        CONCURRENCY:
        - Lock prevents multiple tasks from refreshing simultaneously
        - First task to acquire lock does the refresh
        - Other tasks skip and use existing Valkey cache
        """
        current_time = time.time()

        # Check if refresh needed (outside lock for performance)
        if (current_time - self._last_refresh) < self._refresh_interval:
            return

        # Acquire lock to prevent concurrent refreshes
        async with self._refresh_lock:
            # Double-check after acquiring lock
            if (current_time - self._last_refresh) < self._refresh_interval:
                return

            try:
                # Ensure Valkey client is initialized
                await self._ensure_redis()

                # Load from SSM
                config_data = self._ssm_client.get_parameter_json(self._ssm_parameter, logger)

                if config_data and self._redis:
                    # Update Valkey with TTL using set with expiry
                    from glide import ExpirySet, ExpiryType

                    await self._redis.set(
                        self._redis_key,
                        json.dumps(config_data),
                        expiry=ExpirySet(ExpiryType.SEC, self._redis_ttl),
                    )
                    logger.info(
                        "Guardrail config refreshed in Valkey",
                        extra={
                            "event.name": "guardrail_config_refreshed",
                            "config_keys": len(config_data),
                        },
                    )

                self._last_refresh = current_time

            except Exception as e:
                logger.error(
                    f"Failed to refresh guardrail config: {e}",
                    extra={"event.name": "guardrail_refresh_error", "error.message": str(e)},
                )

    async def _get_guardrail_config(self) -> dict:
        """Get guardrail configuration from Redis with SSM fallback.

        LOOKUP FLOW:
        1. Trigger background refresh if needed (non-blocking)
        2. Try Redis first (1-2ms, shared cache)
        3. On Redis failure, fallback to SSM (50-100ms)

        Returns
        -------
            Guardrail configuration dict
        """
        # Ensure config is fresh (background refresh)
        await self._ensure_config_fresh()

        # Ensure Valkey client is initialized
        await self._ensure_redis()

        # Try Redis first
        if self._redis:
            try:
                cached = await self._redis.get(self._redis_key)
                if cached:
                    # Decode bytes to string
                    cached_str = cached.decode("utf-8") if isinstance(cached, bytes) else cached
                    return json.loads(cached_str)
                logger.debug(
                    "Redis cache miss for guardrail config",
                    extra={"event.name": "guardrail_cache_miss"},
                )
            except Exception as e:
                logger.warning(
                    f"Redis failed, falling back to SSM: {e}",
                    extra={"event.name": "guardrail_redis_failure", "error.message": str(e)},
                )

        # Fallback to SSM
        return self._ssm_client.get_parameter_json(self._ssm_parameter, logger) or {}

    async def get_guardrail_config(
        self, logical_id: str, shared_account_id: str
    ) -> dict[str, str] | None:
        """Get guardrail configuration for logical ID from shared account.

        Uses Redis-backed cache for sub-millisecond lookups with automatic
        SSM refresh in the background.

        Args:
        ----
            logical_id: Logical guardrail ID (e.g., "baseline-security").
            shared_account_id: Shared account ID where guardrails are deployed.

        Returns:
        -------
            Dict with guardrail_id and version, or None if not found.
        """
        try:
            # Get current guardrail configuration (Redis or SSM)
            guardrail_config = await self._get_guardrail_config()

            # Look up logical ID, then account-specific mapping
            logical_config = guardrail_config.get(logical_id, {})
            account_config = logical_config.get(shared_account_id)

            if account_config:
                return {
                    "guardrailIdentifier": account_config["guardrail_id"],
                    "guardrailVersion": account_config["version"],
                    "trace": "enabled",
                }

            logger.warning(
                f"No guardrail mapping found for '{logical_id}' in shared account '{shared_account_id}'"
            )
            return None
        except Exception as e:
            logger.error(f"Error getting guardrail config: {e}")
            return None

    async def get_available_guardrails(self) -> list[str]:
        """Get list of available logical guardrail IDs from all shared accounts.

        Returns
        -------
            List of available logical guardrail IDs.
        """
        guardrail_config = await self._get_guardrail_config()
        return sorted(guardrail_config.keys())
