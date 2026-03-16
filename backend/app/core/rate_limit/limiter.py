# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Async rate limiter using FixedWindow strategy.

This module implements rate limiting for GenAI APIs with two key metrics:
1. RPM (Requests Per Minute): Limits number of API calls
2. TPM (Tokens Per Minute): Limits token consumption for cost control

The FixedWindow approach divides time into 1-minute buckets, resetting
counters at minute boundaries (e.g., 10:30:00, 10:31:00, 10:32:00).
"""

import time

from services.valkey_service import create_valkey_client
from util.constants import RATELIMIT_UNLIMITED


class RateLimiter:
    """Async-optimized rate limiter with O(1) performance.

    STRATEGY: FixedWindow (resets every minute at :00 seconds)
    - Pro: O(1) performance, predictable memory usage
    - Con: Allows burst at window boundaries (up to 2x limit in 1 second)

    USAGE PATTERNS:
    - RPM (Requests Per Minute): tokens=1, tracks request count
    - TPM (Tokens Per Minute): tokens=estimated_input_tokens, tracks token consumption

    REDIS KEYS:
    - "client1:claude:rpm" → tracks requests per minute for client1 using claude
    - "client1:claude:tpm" → tracks tokens per minute for client1 using claude
    """

    def __init__(self):
        """Initialize rate limiter with valkey-glide client."""
        self.valkey = None

    async def _ensure_client(self):
        """Ensure Valkey client is initialized."""
        if self.valkey is None:
            self.valkey = await create_valkey_client()

    def _get_window_expiry(self) -> int:
        """Get current minute window timestamp.

        Returns
        -------
            Unix timestamp of current minute boundary (e.g., 1234567860 for 10:31:00)
        """
        return int(time.time() / 60) * 60

    async def check_and_consume(self, key: str, limit: int, tokens: int = 1) -> tuple[bool, int]:
        """Check and consume rate limit tokens asynchronously with usage tracking.

        Used for token updates after response. For rate limiting, use check_and_consume_all.

        Args:
        ----
            key: Rate limit key identifying what to limit (e.g., "client:model:rpm")
            limit: Maximum tokens allowed per minute (-1 for unlimited)
            tokens: Number of tokens to consume (1 for RPM, estimated_tokens for TPM)

        Returns:
        -------
            Tuple of (success, current_usage):
            - success: True if tokens were consumed successfully, False if limit exceeded
            - current_usage: Current consumption in this minute window
        """
        await self._ensure_client()

        # Handle unlimited quotas
        if limit == RATELIMIT_UNLIMITED:
            return (True, 0)

        window_expiry = self._get_window_expiry()
        window_key = f"LIMITER/{key}/{window_expiry}"

        # Use Lua script for atomic check-and-increment
        try:
            lua_script = """
            local current = redis.call('GET', KEYS[1])
            current = tonumber(current) or 0
            if current + tonumber(ARGV[2]) > tonumber(ARGV[1]) then
                return {0, current}
            end
            local new_val = redis.call('INCRBY', KEYS[1], ARGV[2])
            redis.call('EXPIRE', KEYS[1], 60)
            return {1, new_val}
            """

            result = await self.valkey.custom_command(
                ["EVAL", lua_script, "1", window_key, str(limit), str(tokens)]
            )
            success = result[0] == 1
            current_count = result[1]

            return (success, current_count)

        except Exception:
            # Fallback: Simple check without atomicity
            current = await self.valkey.get(window_key)
            # Decode bytes response
            current_count = int(current.decode("utf-8")) if current else 0

            if current_count + tokens > limit:
                return (False, current_count)

            await self.valkey.incrby(window_key, tokens)
            await self.valkey.expire(window_key, 60)
            return (True, current_count + tokens)

    async def check_and_consume_all(
        self,
        client_rpm_key: str,
        client_rpm_limit: int,
        client_tpm_key: str,
        client_tpm_limit: int,
        account_rpm_key: str,
        account_rpm_limit: int,
        account_tpm_key: str,
        account_tpm_limit: int,
        tokens: int,
    ) -> tuple[bool, int, int, str | None, str | None]:
        """Check and consume all 4 limits (client + account) in single Redis call.

        Uses Lua script to atomically check client RPM, client TPM, account RPM,
        and account TPM. Only increments counters if ALL checks pass.

        Args:
        ----
            client_rpm_key: Client RPM key
            client_rpm_limit: Client RPM limit
            client_tpm_key: Client TPM key
            client_tpm_limit: Client TPM limit
            account_rpm_key: Account RPM key
            account_rpm_limit: Account RPM limit
            account_tpm_key: Account TPM key
            account_tpm_limit: Account TPM limit
            tokens: Tokens to consume

        Returns:
        -------
            Tuple of (success, rpm_used, tpm_used, reason, scope):
            - success: True if all checks passed
            - rpm_used: Current client RPM usage
            - tpm_used: Current client TPM usage
            - reason: 'rpm' or 'tpm' if failed, None if success
            - scope: 'client' or 'account' if failed, None if success
        """
        await self._ensure_client()

        if all(
            lim == RATELIMIT_UNLIMITED
            for lim in [client_rpm_limit, client_tpm_limit, account_rpm_limit, account_tpm_limit]
        ):
            return (True, 0, 0, None, None)

        expiry = self._get_window_expiry()

        try:
            lua_script = """
            local c_rpm = tonumber(redis.call('GET', KEYS[1])) or 0
            local c_tpm = tonumber(redis.call('GET', KEYS[2])) or 0
            local a_rpm = tonumber(redis.call('GET', KEYS[3])) or 0
            local a_tpm = tonumber(redis.call('GET', KEYS[4])) or 0

            if tonumber(ARGV[1]) ~= -1 and c_rpm >= tonumber(ARGV[1]) then
                return {0, c_rpm, c_tpm, 'rpm', 'client'}
            end
            if tonumber(ARGV[2]) ~= -1 and c_tpm + tonumber(ARGV[5]) > tonumber(ARGV[2]) then
                return {0, c_rpm, c_tpm, 'tpm', 'client'}
            end
            if tonumber(ARGV[3]) ~= -1 and a_rpm >= tonumber(ARGV[3]) then
                return {0, c_rpm, c_tpm, 'rpm', 'account'}
            end
            if tonumber(ARGV[4]) ~= -1 and a_tpm + tonumber(ARGV[5]) > tonumber(ARGV[4]) then
                return {0, c_rpm, c_tpm, 'tpm', 'account'}
            end

            if tonumber(ARGV[1]) ~= -1 then
                redis.call('INCR', KEYS[1])
                redis.call('EXPIRE', KEYS[1], 60)
                c_rpm = c_rpm + 1
            end
            if tonumber(ARGV[2]) ~= -1 then
                redis.call('INCRBY', KEYS[2], ARGV[5])
                redis.call('EXPIRE', KEYS[2], 60)
                c_tpm = c_tpm + tonumber(ARGV[5])
            end
            if tonumber(ARGV[3]) ~= -1 then
                redis.call('INCR', KEYS[3])
                redis.call('EXPIRE', KEYS[3], 60)
            end
            if tonumber(ARGV[4]) ~= -1 then
                redis.call('INCRBY', KEYS[4], ARGV[5])
                redis.call('EXPIRE', KEYS[4], 60)
            end

            return {1, c_rpm, c_tpm, '', ''}
            """

            result = await self.valkey.custom_command(
                [
                    "EVAL",
                    lua_script,
                    "4",
                    f"LIMITER/{client_rpm_key}/{expiry}",
                    f"LIMITER/{client_tpm_key}/{expiry}",
                    f"LIMITER/{account_rpm_key}/{expiry}",
                    f"LIMITER/{account_tpm_key}/{expiry}",
                    str(client_rpm_limit),
                    str(client_tpm_limit),
                    str(account_rpm_limit),
                    str(account_tpm_limit),
                    str(tokens),
                ]
            )

            return (
                result[0] == 1,
                result[1],
                result[2],
                result[3] if result[0] == 0 else None,
                result[4] if result[0] == 0 else None,
            )

        except Exception:
            # Fallback to separate checks
            rpm_ok, rpm_used = await self.check_and_consume(client_rpm_key, client_rpm_limit, 1)
            if not rpm_ok:
                tpm_ok, tpm_used = await self.check_and_consume(
                    client_tpm_key, client_tpm_limit, 0
                )
                return (False, rpm_used, tpm_used, "rpm", "client")

            tpm_ok, tpm_used = await self.check_and_consume(
                client_tpm_key, client_tpm_limit, tokens
            )
            if not tpm_ok:
                return (False, rpm_used, tpm_used, "tpm", "client")

            if account_rpm_limit != RATELIMIT_UNLIMITED:
                account_rpm_ok, _ = await self.check_and_consume(
                    account_rpm_key, account_rpm_limit, 1
                )
                if not account_rpm_ok:
                    return (False, rpm_used, tpm_used, "rpm", "account")

            if account_tpm_limit != RATELIMIT_UNLIMITED:
                account_tpm_ok, _ = await self.check_and_consume(
                    account_tpm_key, account_tpm_limit, tokens
                )
                if not account_tpm_ok:
                    return (False, rpm_used, tpm_used, "tpm", "account")

            return (True, rpm_used, tpm_used, None, None)

    def get_reset_time(self) -> int:
        """Get next window reset time for rate limit headers.

        FixedWindow strategy resets counters at minute boundaries (e.g., 10:30:00, 10:31:00).
        This calculates when the current window ends and counters reset to 0.

        Example:
        - Current time: 10:30:45 → Reset at: 10:31:00 (15 seconds from now)
        - Current time: 10:30:00 → Reset at: 10:31:00 (60 seconds from now)

        Returns:
        -------
            Unix timestamp when the current rate limit window resets
        """
        current_time = int(time.time())
        # Calculate seconds until next minute boundary
        seconds_until_reset = 60 - (current_time % 60)
        return current_time + seconds_until_reset
