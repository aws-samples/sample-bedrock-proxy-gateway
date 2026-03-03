"""JWKS (JSON Web Key Set) handling module."""

import logging
import time

import requests

logger = logging.getLogger(__name__)


class JWKSCache:
    """Cache for JWKS keys with rotation support.

    Attributes
    ----------
        _keys: Cached JWKS data.
        _last_fetch: Timestamp of last key fetch.
        _cache_ttl: Cache time-to-live in seconds.
    """

    def __init__(self):
        self._keys = None
        self._last_fetch = 0
        self._cache_ttl = 86400  # 1 day cache to balance security and performance

    def get_rsa_key(self, jwks_url: str) -> dict | None:
        """Get JWKS data from URL with caching.

        Args:
        ----
            jwks_url (str): URL to fetch JWKS from.

        Returns:
        -------
            Optional[dict]: JWKS data if found, None otherwise.
        """
        current_time = time.time()

        # Refresh cache if expired or empty - this reduces JWKS endpoint load
        if not self._keys or (current_time - self._last_fetch) > self._cache_ttl:
            try:
                # Fetch JWKS with timeout to prevent hanging requests
                response = requests.get(jwks_url, timeout=10)
                response.raise_for_status()
                self._keys = response.json()
                self._last_fetch = current_time

            except Exception as e:
                logger.error(f"Failed to fetch JWKS: {e}")
                # Graceful degradation: use cached key if JWKS fetch fails
                if not self._keys:  # Only fail if no cached key available
                    return None

        return self._keys


# Global JWKS cache instance
jwks_cache = JWKSCache()
