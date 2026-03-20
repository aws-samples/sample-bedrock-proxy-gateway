# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for routes.operational_routes module."""

import time
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from routes.operational_routes import setup_operational_routes


class TestOperationalRoutes:
    """Test cases for operational cache management routes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_cache = {}
        self.cache_patcher = patch("routes.operational_routes._memory_cache", self.mock_cache)
        self.cache_patcher.start()

        self.regular_client_id = "CCREGULARCLIENTID123456789"
        self.admin_client_id_test = "EXAMPLECLIENTID123456789ABCDEF"
        self.admin_client_id_prod = "CCMCKKPFTOCVXTZEHMYTLGDLCOPAPNHQ"

    def teardown_method(self):
        """Clean up after each test."""
        self.cache_patcher.stop()
        self.mock_cache.clear()

    def _get_endpoint(self, path: str, method: str = "GET"):
        """Get endpoint function from router."""
        router = setup_operational_routes()
        for route in router.routes:
            if hasattr(route, "path") and route.path == path and method in route.methods:
                return route.endpoint
        return None

    def _populate_cache(self, client_id: str, num_keys: int = 3):
        """Populate cache with test data."""
        for i in range(num_keys):
            key = f"quota:{client_id}:model-{i}"
            self.mock_cache[key] = {"data": f"test-data-{i}", "expiry": time.time() + 300}

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_list_cache_keys_regular_user(self, mock_context):
        """Test listing cache keys as regular user."""
        mock_context.get.return_value = self.regular_client_id

        self._populate_cache(self.regular_client_id, 3)
        self._populate_cache("OTHER_CLIENT", 2)

        endpoint = self._get_endpoint("/cache/keys", "GET")
        response = await endpoint()

        assert response["client_id"] == self.regular_client_id
        assert response["is_admin"] is False
        assert response["count"] == 3
        assert len(response["keys"]) == 3
        assert all(key.startswith(f"quota:{self.regular_client_id}:") for key in response["keys"])

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    @patch("routes.operational_routes.scope_context")
    async def test_list_cache_keys_admin_test(self, mock_scope_context, mock_client_context):
        """Test listing cache keys as admin in test environment."""
        mock_client_context.get.return_value = self.admin_client_id_test
        mock_scope_context.get.return_value = "bedrockproxygateway:admin"

        self._populate_cache("CLIENT_A", 2)
        self._populate_cache("CLIENT_B", 3)

        endpoint = self._get_endpoint("/cache/keys", "GET")
        response = await endpoint()

        assert response["client_id"] == self.admin_client_id_test
        assert response["is_admin"] is True
        assert response["count"] == 5
        assert len(response["keys"]) == 5

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    @patch("routes.operational_routes.scope_context")
    async def test_list_cache_keys_admin_prod(self, mock_scope_context, mock_client_context):
        """Test listing cache keys as admin in prod environment."""
        mock_client_context.get.return_value = self.admin_client_id_prod
        mock_scope_context.get.return_value = "bedrockproxygateway:admin"

        self._populate_cache("CLIENT_A", 2)

        endpoint = self._get_endpoint("/cache/keys", "GET")
        response = await endpoint()

        assert response["is_admin"] is True
        assert response["count"] == 2

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_list_cache_keys_no_client_id(self, mock_context):
        """Test listing cache keys without client_id in context."""
        mock_context.get.return_value = None

        endpoint = self._get_endpoint("/cache/keys", "GET")

        with pytest.raises(HTTPException) as exc_info:
            await endpoint()

        assert exc_info.value.status_code == 401
        assert "Client ID not found in context" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_list_cache_keys_empty_cache(self, mock_context):
        """Test listing cache keys when cache is empty."""
        mock_context.get.return_value = self.regular_client_id

        endpoint = self._get_endpoint("/cache/keys", "GET")
        response = await endpoint()

        assert response["count"] == 0
        assert response["keys"] == []

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_all_cache_keys_regular_user(self, mock_context):
        """Test clearing all cache keys as regular user."""
        mock_context.get.return_value = self.regular_client_id

        self._populate_cache(self.regular_client_id, 3)
        self._populate_cache("OTHER_CLIENT", 2)

        endpoint = self._get_endpoint("/cache/keys", "DELETE")
        response = await endpoint()

        assert response["client_id"] == self.regular_client_id
        assert response["is_admin"] is False
        assert response["keys_cleared"] == 3
        assert response["message"] == "Cache cleared successfully"
        assert len(self.mock_cache) == 2

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    @patch("routes.operational_routes.scope_context")
    async def test_clear_all_cache_keys_admin(self, mock_scope_context, mock_client_context):
        """Test clearing all cache keys as admin."""
        mock_client_context.get.return_value = self.admin_client_id_prod
        mock_scope_context.get.return_value = "bedrockproxygateway:admin"

        self._populate_cache("CLIENT_A", 2)
        self._populate_cache("CLIENT_B", 3)

        endpoint = self._get_endpoint("/cache/keys", "DELETE")
        response = await endpoint()

        assert response["is_admin"] is True
        assert response["keys_cleared"] == 5
        assert len(self.mock_cache) == 0

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_all_cache_keys_no_client_id(self, mock_context):
        """Test clearing all cache keys without client_id in context."""
        mock_context.get.return_value = None

        endpoint = self._get_endpoint("/cache/keys", "DELETE")

        with pytest.raises(HTTPException) as exc_info:
            await endpoint()

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_cache_by_key_regular_user_own_key(self, mock_context):
        """Test clearing specific cache key as regular user (own key)."""
        mock_context.get.return_value = self.regular_client_id

        self._populate_cache(self.regular_client_id, 3)
        cache_key = f"quota:{self.regular_client_id}:model-0"

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")
        response = await endpoint(cache_key)

        assert response["client_id"] == self.regular_client_id
        assert response["is_admin"] is False
        assert response["key"] == cache_key
        assert response["message"] == "Cache key cleared successfully"
        assert cache_key not in self.mock_cache
        assert len(self.mock_cache) == 2

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_cache_by_key_regular_user_other_key(self, mock_context):
        """Test clearing specific cache key as regular user (other user's key)."""
        mock_context.get.return_value = self.regular_client_id

        self._populate_cache("OTHER_CLIENT", 2)
        cache_key = "quota:OTHER_CLIENT:model-0"

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")

        with pytest.raises(HTTPException) as exc_info:
            await endpoint(cache_key)

        assert exc_info.value.status_code == 403
        assert "You can only clear your own cache keys" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    @patch("routes.operational_routes.scope_context")
    async def test_clear_cache_by_key_admin(self, mock_scope_context, mock_client_context):
        """Test clearing specific cache key as admin."""
        mock_client_context.get.return_value = self.admin_client_id_prod
        mock_scope_context.get.return_value = "bedrockproxygateway:admin"

        self._populate_cache("OTHER_CLIENT", 2)
        cache_key = "quota:OTHER_CLIENT:model-0"

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")
        response = await endpoint(cache_key)

        assert response["is_admin"] is True
        assert response["key"] == cache_key
        assert cache_key not in self.mock_cache

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_cache_by_key_not_found(self, mock_context):
        """Test clearing non-existent cache key."""
        mock_context.get.return_value = self.regular_client_id

        cache_key = f"quota:{self.regular_client_id}:nonexistent"

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")

        with pytest.raises(HTTPException) as exc_info:
            await endpoint(cache_key)

        assert exc_info.value.status_code == 404
        assert f"Cache key '{cache_key}' not found" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_cache_by_key_no_client_id(self, mock_context):
        """Test clearing cache key without client_id in context."""
        mock_context.get.return_value = None

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")

        with pytest.raises(HTTPException) as exc_info:
            await endpoint("some-key")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("routes.operational_routes.client_id_context")
    async def test_clear_cache_by_key_with_path_separator(self, mock_context):
        """Test clearing cache key containing path separators."""
        mock_context.get.return_value = self.regular_client_id

        cache_key = f"quota:{self.regular_client_id}:us.amazon.nova-lite-v1:0"
        self.mock_cache[cache_key] = {"data": "test", "expiry": time.time() + 300}

        endpoint = self._get_endpoint("/cache/keys/{cache_key:path}", "DELETE")
        response = await endpoint(cache_key)

        assert response["client_id"] == self.regular_client_id
        assert cache_key not in self.mock_cache
