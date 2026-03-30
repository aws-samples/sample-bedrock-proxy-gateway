# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.rate_limit.limiter module."""

from unittest.mock import AsyncMock, patch

import pytest
from core.rate_limit.limiter import RateLimiter
from util.constants import RATELIMIT_UNLIMITED


class TestRateLimiter:
    """Test cases for RateLimiter class."""

    def setup_method(self):
        """Reset global client before each test."""
        import services.valkey_service

        services.valkey_service._client = None

    @pytest.mark.asyncio
    async def test_check_and_consume_unlimited(self):
        """Test check_and_consume with unlimited quota."""
        mock_client = AsyncMock()

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume("test:key", RATELIMIT_UNLIMITED, 100)
            assert result == (True, 0)

    @pytest.mark.asyncio
    async def test_check_and_consume_success(self):
        """Test check_and_consume when limit not exceeded."""
        mock_client = AsyncMock()
        mock_client.custom_command.return_value = [1, 50]

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume("client:model:rpm", 100, 1)
            assert result == (True, 50)

    @pytest.mark.asyncio
    async def test_check_and_consume_exceeded(self):
        """Test check_and_consume when limit exceeded."""
        mock_client = AsyncMock()
        mock_client.custom_command.return_value = [0, 100]

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume("client:model:rpm", 100, 1)
            assert result == (False, 100)

    @pytest.mark.asyncio
    async def test_check_and_consume_fallback(self):
        """Test check_and_consume fallback when Lua script fails."""
        mock_client = AsyncMock()
        mock_client.custom_command.side_effect = Exception("Valkey error")
        mock_client.get.return_value = b"50"

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume("client:model:tpm", 1000, 100)
            assert result == (True, 150)

    @pytest.mark.asyncio
    async def test_check_and_consume_all_success(self):
        """Test check_and_consume_all when all limits pass."""
        mock_client = AsyncMock()
        mock_client.custom_command.return_value = [1, 50, 500, "", ""]

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume_all(
                "client:model:rpm",
                100,
                "client:model:tpm",
                1000,
                "account:model:rpm",
                50,
                "account:model:tpm",
                500,
                100,
            )
            assert result == (True, 50, 500, None, None)

    @pytest.mark.asyncio
    async def test_check_and_consume_all_exceeded(self):
        """Test check_and_consume_all when limit exceeded."""
        mock_client = AsyncMock()
        mock_client.custom_command.return_value = [0, 100, 500, "rpm", "client"]

        async def mock_create():
            return mock_client

        with patch("core.rate_limit.limiter.create_valkey_client", side_effect=mock_create):
            rate_limiter = RateLimiter()
            result = await rate_limiter.check_and_consume_all(
                "client:model:rpm",
                100,
                "client:model:tpm",
                1000,
                "account:model:rpm",
                50,
                "account:model:tpm",
                500,
                100,
            )
            assert result == (False, 100, 500, "rpm", "client")

    def test_get_reset_time(self):
        """Test get_reset_time returns next minute boundary."""
        with patch("time.time", return_value=1234567845):
            rate_limiter = RateLimiter()
            reset_time = rate_limiter.get_reset_time()
            assert reset_time == 1234567860
            assert reset_time % 60 == 0
