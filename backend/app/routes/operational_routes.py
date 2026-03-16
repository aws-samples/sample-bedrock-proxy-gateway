# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Operational API routes for cache management."""

from core.cache.memory_cache import _memory_cache
from fastapi import APIRouter, HTTPException, status
from observability.context_vars import client_id_context, scope_context
from util.constants import SCOPE_BEDROCKPROXY_ADMIN


def setup_operational_routes():
    """Configure operational API routes.

    Returns
    -------
        APIRouter: Configured operational router with cache management endpoints.
    """
    operational_router = APIRouter()

    def _is_admin() -> bool:
        """Check if current user has bedrockproxygateway:admin scope."""
        scope = scope_context.get()
        if not scope:
            return False
        scopes = scope.split() if isinstance(scope, str) else [scope]
        return SCOPE_BEDROCKPROXY_ADMIN in scopes

    def _get_client_keys(client_id: str) -> list[str]:
        """Get cache keys for specific client."""
        return [key for key in _memory_cache if key.startswith(f"quota:{client_id}:")]

    @operational_router.get("/cache/keys")
    async def list_cache_keys():
        """List cache keys.

        Admin users see all keys, regular users see only their own keys.

        Returns
        -------
            dict: List of cache keys.
        """
        client_id = client_id_context.get()
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client ID not found in context",
            )

        keys = list(_memory_cache.keys()) if _is_admin() else _get_client_keys(client_id)

        return {"client_id": client_id, "is_admin": _is_admin(), "keys": keys, "count": len(keys)}

    @operational_router.delete("/cache/keys")
    async def clear_all_cache_keys():
        """Clear all cache keys.

        Admin users clear all keys, regular users clear only their own keys.

        Returns
        -------
            dict: Number of keys cleared.
        """
        client_id = client_id_context.get()
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client ID not found in context",
            )

        if _is_admin():
            count = len(_memory_cache)
            _memory_cache.clear()
        else:
            keys = _get_client_keys(client_id)
            for key in keys:
                _memory_cache.pop(key, None)
            count = len(keys)

        return {
            "client_id": client_id,
            "is_admin": _is_admin(),
            "keys_cleared": count,
            "message": "Cache cleared successfully",
        }

    @operational_router.delete("/cache/keys/{cache_key:path}")
    async def clear_cache_by_key(cache_key: str):
        """Clear specific cache key.

        Admin users can clear any key, regular users can only clear their own keys.

        Args:
        ----
            cache_key: Cache key to clear.

        Returns:
        -------
            dict: Confirmation of key deletion.
        """
        client_id = client_id_context.get()
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client ID not found in context",
            )

        # Check if key exists
        if cache_key not in _memory_cache:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Cache key '{cache_key}' not found",
            )

        # Regular users can only clear their own keys
        if not _is_admin() and not cache_key.startswith(f"quota:{client_id}:"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only clear your own cache keys",
            )

        _memory_cache.pop(cache_key, None)

        return {
            "client_id": client_id,
            "is_admin": _is_admin(),
            "key": cache_key,
            "message": "Cache key cleared successfully",
        }

    return operational_router
