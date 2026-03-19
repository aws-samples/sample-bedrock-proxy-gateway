# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for generic in-memory cache."""

import asyncio
import time
from unittest.mock import patch

import pytest
from core.cache.memory_cache import _memory_cache, get_cache, set_cache


class TestMemoryCache:
    """Test class for generic memory cache functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        _memory_cache.clear()

    @pytest.mark.asyncio
    async def test_set_and_get_success(self):
        """Test successful set and get operations."""
        cache_key = "test:key"
        data = {"key": "value", "number": 42}

        await set_cache(cache_key, data, 300)
        result = await get_cache(cache_key)

        assert result == data

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Test getting data for non-existent key."""
        result = await get_cache("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_data_cleanup(self):
        """Test expired data is removed from cache."""
        cache_key = "test:expired"
        data = "expired_data"

        await set_cache(cache_key, data, 0)
        await asyncio.sleep(0.1)

        result = await get_cache(cache_key)
        assert result is None
        assert cache_key not in _memory_cache

    @pytest.mark.asyncio
    async def test_default_expiration(self):
        """Test default expiration time."""
        cache_key = "test:default"
        data = "test_data"

        await set_cache(cache_key, data)

        cached_item = _memory_cache[cache_key]
        expected_expiry = time.time() + 300
        assert abs(cached_item["expiry"] - expected_expiry) < 1

    @pytest.mark.asyncio
    async def test_custom_expiration(self):
        """Test custom expiration time."""
        cache_key = "test:custom"
        data = "test_data"
        custom_expiry = 600

        await set_cache(cache_key, data, custom_expiry)

        cached_item = _memory_cache[cache_key]
        expected_expiry = time.time() + custom_expiry
        assert abs(cached_item["expiry"] - expected_expiry) < 1

    @pytest.mark.asyncio
    async def test_different_data_types(self):
        """Test caching different data types."""
        test_cases = [
            ("string", "test_string"),
            ("number", 123),
            ("list", [1, 2, 3]),
            ("dict", {"nested": "value"}),
            ("none", None),
        ]

        for key, data in test_cases:
            await set_cache(key, data)
            result = await get_cache(key)
            assert result == data

    @pytest.mark.asyncio
    async def test_overwrite_existing_key(self):
        """Test overwriting existing cache entry."""
        cache_key = "test:overwrite"

        await set_cache(cache_key, "initial")
        await set_cache(cache_key, "updated")

        result = await get_cache(cache_key)
        assert result == "updated"

    @pytest.mark.asyncio
    async def test_get_exception_handling(self):
        """Test exception handling in get operation."""
        with patch("core.cache.memory_cache._memory_cache") as mock_cache:
            mock_cache.get.side_effect = Exception("Cache error")
            result = await get_cache("test")
            assert result is None

    @pytest.mark.asyncio
    async def test_set_exception_handling(self):
        """Test exception handling in set operation."""
        with (
            patch("core.cache.memory_cache.time.time", side_effect=Exception("Time error")),
            patch("core.cache.memory_cache.logger") as mock_logger,
        ):
            await set_cache("test", "data")
            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_structure_integrity(self):
        """Test cache structure contains expected keys."""
        cache_key = "test:structure"
        data = "test_data"

        await set_cache(cache_key, data)

        assert cache_key in _memory_cache
        cached_item = _memory_cache[cache_key]
        assert "data" in cached_item
        assert "expiry" in cached_item
        assert isinstance(cached_item["expiry"], float)

    @pytest.mark.asyncio
    async def test_multiple_cache_entries(self):
        """Test multiple cache entries work independently."""
        await set_cache("key1", "value1")
        await set_cache("key2", "value2")

        result1 = await get_cache("key1")
        result2 = await get_cache("key2")

        assert result1 == "value1"
        assert result2 == "value2"

    @pytest.mark.asyncio
    async def test_zero_expiration(self):
        """Test zero expiration time."""
        cache_key = "test:zero"
        data = "zero_data"

        await set_cache(cache_key, data, 0)

        # Should be immediately expired
        result = await get_cache(cache_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_negative_expiration(self):
        """Test negative expiration time."""
        cache_key = "test:negative"
        data = "negative_data"

        await set_cache(cache_key, data, -100)

        # Should be immediately expired
        result = await get_cache(cache_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_credentials_format(self):
        """Test caching AWS credentials format."""
        cache_key = "test:credentials"
        credentials = {
            "AccessKeyId": "test-access-key",
            "SecretAccessKey": "test-secret-key",
            "SessionToken": "test-session-token",
        }

        await set_cache(cache_key, credentials, 3600)
        result = await get_cache(cache_key)

        assert result["AccessKeyId"] == "test-access-key"
        assert result["SecretAccessKey"] == "test-secret-key"
        assert result["SessionToken"] == "test-session-token"
