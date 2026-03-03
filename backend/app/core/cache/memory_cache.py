"""Generic in-memory caching module."""

import logging
import time
from typing import Any

# Module-level logger for cache operations
logger = logging.getLogger(__name__)

# In-memory cache storage
# Structure: {cache_key: {"data": Any, "expiry": timestamp}}
_memory_cache: dict[str, dict[str, Any]] = {}


async def get_cache(cache_key: str) -> Any | None:
    """Get data from in-memory cache.

    Args:
    ----
        cache_key: Cache key for the data.

    Returns:
    -------
        Data if found and not expired, None otherwise.
    """
    try:
        cached_item = _memory_cache.get(cache_key)

        if not cached_item:
            return None

        # Check if data is expired
        if cached_item["expiry"] < time.time():
            del _memory_cache[cache_key]
            return None

        return cached_item["data"]

    except Exception as e:
        logger.error(f"In-memory cache get failed for key {cache_key}: {e}")
        return None


async def set_cache(cache_key: str, data: Any, expiration: int = 300) -> None:
    """Set data in in-memory cache.

    Args:
    ----
        cache_key: Cache key for the data.
        data: Data to cache.
        expiration: Expiration time in seconds.
    """
    try:
        _memory_cache[cache_key] = {
            "data": data,
            "expiry": time.time() + expiration,
        }

    except Exception as e:
        logger.error(f"In-memory cache set failed for key {cache_key}: {e}")
