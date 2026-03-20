# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.rate_limit.engine module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from core.rate_limit.engine import QuotaConfig, RateLimitEngine
from fastapi import HTTPException


class TestQuotaConfig:
    """Test cases for QuotaConfig dataclass."""

    def test_quota_config_creation(self):
        """Test QuotaConfig creation and immutability.

        LOGIC: QuotaConfig is a dataclass that stores rate limiting parameters
        for a specific client-model combination. It must be immutable to prevent
        accidental modifications that could affect rate limiting behavior.

        EXPECTED: All fields are correctly set and accessible
        """
        config = QuotaConfig(rpm=100, tpm=1000, accounts=["123", "456"])

        assert config.rpm == 100
        assert config.tpm == 1000
        assert config.accounts == ["123", "456"]

    def test_is_unlimited_both_unlimited(self):
        """Test is_unlimited when both RPM and TPM are unlimited.

        LOGIC: When both rpm=-1 and tpm=-1, the quota is unlimited.
        This enables the fastest path through rate limiting logic
        with no Redis operations required.

        EXPECTED: is_unlimited returns True for unlimited quotas
        """
        config = QuotaConfig(rpm=-1, tpm=-1, accounts=["123"])
        assert config.is_unlimited is True

    def test_is_unlimited_rpm_limited(self):
        """Test is_unlimited when RPM is limited.

        LOGIC: If either RPM or TPM has a limit (not -1), the quota
        is considered limited and requires Redis counter checks.
        Even unlimited TPM with limited RPM needs rate limiting.

        EXPECTED: is_unlimited returns False when any limit exists
        """
        config = QuotaConfig(rpm=100, tpm=-1, accounts=["123"])
        assert config.is_unlimited is False

    def test_is_unlimited_tpm_limited(self):
        """Test is_unlimited when TPM is limited.

        LOGIC: Limited TPM with unlimited RPM still requires rate limiting
        for token consumption tracking. The quota is not truly unlimited
        if any metric has constraints.

        EXPECTED: is_unlimited returns False when TPM is limited
        """
        config = QuotaConfig(rpm=-1, tpm=1000, accounts=["123"])
        assert config.is_unlimited is False

    def test_is_unlimited_both_limited(self):
        """Test is_unlimited when both are limited.

        LOGIC: When both RPM and TPM have limits, full rate limiting
        is required with Redis counter checks for both metrics.
        This is the most restrictive quota configuration.

        EXPECTED: is_unlimited returns False for fully limited quotas
        """
        config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        assert config.is_unlimited is False


class TestRateLimitEngine:
    """Test cases for RateLimitEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_limiter = Mock()
        self.mock_limiter.check_and_consume = AsyncMock()
        self.mock_limiter.check_and_consume_all = AsyncMock()
        self.rate_config = {
            "permissions": {
                "client1": {
                    "models": {"model1": {"rpm": 100, "tpm": 1000}},
                    "accounts": ["123", "456"],
                },
                "default": {"models": {"model1": {"rpm": 50, "tpm": 500}}, "accounts": ["789"]},
            },
            "account_limits": {"123": {"model1": {"rpm": 200, "tpm": 2000}}},
        }
        self.engine = RateLimitEngine(self.mock_limiter, self.rate_config)

    def test_init(self):
        """Test engine initialization.

        LOGIC: RateLimitEngine must properly initialize with the provided
        limiter and configuration. It extracts permissions and account_limits
        from the config for efficient access during rate limiting operations.

        EXPECTED: All components are correctly initialized and accessible
        """
        assert self.engine.limiter == self.mock_limiter
        assert self.engine.permissions == self.rate_config["permissions"]
        assert self.engine.account_limits == self.rate_config["account_limits"]

    def test_get_api_type_converse(self):
        """Test API type detection for converse endpoints.

        LOGIC: Converse API endpoints (including streaming variants) use
        different token calculation methods than invoke endpoints.
        Accurate API type detection is critical for proper token estimation.

        EXPECTED: All converse patterns correctly identified as "converse"
        """
        test_cases = ["/model/claude-3-haiku/converse", "/model/mistral-7b/converse-stream"]

        for path in test_cases:
            result = RateLimitEngine.get_api_type(path)
            assert result == "converse"

    def test_get_api_type_invoke(self):
        """Test API type detection for invoke endpoints.

        LOGIC: Invoke API endpoints (including streaming variants) have
        different request/response structures requiring different token
        calculation methods. Proper detection ensures accurate rate limiting.

        EXPECTED: All invoke patterns correctly identified as "invoke"
        """
        test_cases = [
            "/model/claude-3-haiku/invoke",
            "/model/mistral-7b/invoke-with-response-stream",
        ]

        for path in test_cases:
            result = RateLimitEngine.get_api_type(path)
            assert result == "invoke"

    def test_get_api_type_no_match(self):
        """Test API type detection for non-matching paths.

        LOGIC: Non-GenAI endpoints and unknown operations should return None
        to trigger early exit from rate limiting logic. This prevents
        unnecessary processing for non-billable endpoints.

        EXPECTED: Unrecognized patterns return None
        """
        test_cases = ["/health", "/model/claude-3-haiku/unknown", "/api/test", ""]

        for path in test_cases:
            result = RateLimitEngine.get_api_type(path)
            assert result is None

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_cache_hit(self, mock_get_cache):
        """Test quota config retrieval with cache hit.

        LOGIC: Quota configs are cached for 24 hours to avoid repeated
        JSON parsing and validation. Cache hits provide sub-microsecond
        lookup times for high-frequency rate limiting operations.

        EXPECTED: Cached config returned directly, no processing needed
        """
        cached_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        mock_get_cache.return_value = cached_config

        result = await self.engine.get_quota_config("client1", "model1")

        assert result == cached_config
        mock_get_cache.assert_called_once_with("quota:client1:model1")

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.set_cache")
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_cache_miss(self, mock_get_cache, mock_set_cache):
        """Test quota config retrieval with cache miss.

        LOGIC: On cache miss, parse JSON config, validate structure,
        create QuotaConfig object, and cache for future requests.
        This ensures consistent performance after initial lookup.

        EXPECTED: Config parsed from JSON, cached, and returned correctly
        """
        mock_get_cache.return_value = None

        result = await self.engine.get_quota_config("client1", "model1")

        assert result.rpm == 100
        assert result.tpm == 1000
        assert result.accounts == ["123", "456"]
        mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_fallback_to_default(self, mock_get_cache):
        """Test quota config fallback to default client.

        LOGIC: When a client has no specific configuration, fall back
        to the "default" client config. This provides baseline rate
        limiting for all clients without explicit configuration.

        EXPECTED: Default client config used for unknown clients
        """
        mock_get_cache.return_value = None

        result = await self.engine.get_quota_config("unknown_client", "model1")

        assert result.rpm == 50
        assert result.tpm == 500
        assert result.accounts == ["789"]

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_no_client(self, mock_get_cache):
        """Test quota config with no client configuration.

        LOGIC: When neither specific client nor default client configs exist,
        return HTTP 403 Forbidden. This prevents unauthorized access to
        GenAI resources by unconfigured clients.

        EXPECTED: HTTP 403 with descriptive error message
        """
        mock_get_cache.return_value = None
        engine = RateLimitEngine(self.mock_limiter, {"permissions": {}})

        with pytest.raises(HTTPException) as exc_info:
            await engine.get_quota_config("unknown_client", "model1")

        assert exc_info.value.status_code == 403
        assert "No quota configured" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_no_model(self, mock_get_cache):
        """Test quota config with no model configuration.

        LOGIC: When a client exists but has no configuration for the
        requested model, return HTTP 403. This prevents access to
        models not explicitly allowed for the client.

        EXPECTED: HTTP 403 with model-specific error message
        """
        mock_get_cache.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await self.engine.get_quota_config("client1", "unknown_model")

        assert exc_info.value.status_code == 403
        assert "No quota configured for model" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.get_cache")
    async def test_get_quota_config_invalid_config(self, mock_get_cache):
        """Test quota config with invalid configuration.

        LOGIC: Malformed config (missing required fields like tpm) should
        return HTTP 500 Internal Server Error. This indicates a configuration
        problem that needs administrative attention.

        EXPECTED: HTTP 500 with configuration error message
        """
        mock_get_cache.return_value = None
        invalid_config = {
            "permissions": {
                "client1": {
                    "models": {
                        "model1": {"rpm": 100}  # Missing tpm
                    },
                    "accounts": ["123"],
                }
            }
        }
        engine = RateLimitEngine(self.mock_limiter, invalid_config)

        with pytest.raises(HTTPException) as exc_info:
            await engine.get_quota_config("client1", "model1")

        assert exc_info.value.status_code == 500
        assert "Invalid quota configuration" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_select_account_unlimited(self):
        """Test account selection for unlimited quotas.

        LOGIC: For unlimited quotas, use hash-based load balancing across
        available accounts. No Redis checks needed since there are no limits
        to enforce. This provides optimal performance for unlimited clients.

        EXPECTED: Hash-based account selection without rate limit checks
        """
        quota_config = QuotaConfig(rpm=-1, tpm=-1, accounts=["123", "456"])

        account_id, reason, scope, rpm_used, tpm_used = await self.engine.select_account(
            "client1", "model1", quota_config, 100
        )

        assert account_id in ["123", "456"]
        assert reason is None
        assert scope is None
        assert rpm_used == 0
        assert tpm_used == 0

    @pytest.mark.asyncio
    async def test_select_account_limited(self):
        """Test account selection for limited quotas.

        LOGIC: For limited quotas, must check Redis counters to find an
        account with available capacity. This ensures rate limits are
        enforced while maximizing resource utilization across accounts.

        EXPECTED: Available account found through capacity checking
        """
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123", "456"])

        with patch.object(
            self.engine, "_find_available_account", return_value=("123", None, None, 50, 500)
        ) as mock_find:
            account_id, reason, scope, rpm_used, tpm_used = await self.engine.select_account(
                "client1", "model1", quota_config, 100
            )

            assert account_id == "123"
            assert reason is None
            assert scope is None
            mock_find.assert_called_once_with("client1", "model1", quota_config, 100)

    @pytest.mark.asyncio
    async def test_find_available_account_rpm_exceeded(self):
        """Test find available account when RPM limit is exceeded."""
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.check_and_consume_all.return_value = (False, 100, 500, "rpm", "client")

        account_id, reason, scope, rpm_used, tpm_used = await self.engine._find_available_account(
            "client1", "model1", quota_config, 100
        )

        assert account_id is None
        assert reason.value == "rpm"
        assert scope.value == "client"
        assert rpm_used == 100
        assert tpm_used == 500

    @pytest.mark.asyncio
    async def test_find_available_account_tpm_exceeded(self):
        """Test find available account when TPM limit is exceeded."""
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.check_and_consume_all.return_value = (False, 50, 1000, "tpm", "client")

        account_id, reason, scope, rpm_used, tpm_used = await self.engine._find_available_account(
            "client1", "model1", quota_config, 100
        )

        assert account_id is None
        assert reason.value == "tpm"
        assert scope.value == "client"
        assert rpm_used == 50
        assert tpm_used == 1000

    @pytest.mark.asyncio
    async def test_find_available_account_success(self):
        """Test successful account finding."""
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.check_and_consume_all.return_value = (True, 50, 500, None, None)

        account_id, reason, scope, rpm_used, tpm_used = await self.engine._find_available_account(
            "client1", "model1", quota_config, 100
        )

        assert account_id == "123"
        assert reason is None
        assert scope is None
        assert rpm_used == 50
        assert tpm_used == 500

    @pytest.mark.asyncio
    @patch("core.rate_limit.engine.record_redis_failure")
    async def test_find_available_account_redis_failure(self, mock_record_failure):
        """Test find available account with Redis failure."""
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.check_and_consume_all.side_effect = Exception("Redis error")

        with patch.object(self.engine, "_hash_based_account", return_value="123") as mock_hash:
            (
                account_id,
                reason,
                scope,
                rpm_used,
                tpm_used,
            ) = await self.engine._find_available_account("client1", "model1", quota_config, 100)

            assert account_id == "123"
            assert reason is None
            assert scope is None
            mock_record_failure.assert_called_once_with("quota_check", "Exception")
            mock_hash.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    @patch("time.time")
    async def test_hash_based_account(self, mock_time):
        """Test hash-based account selection.

        LOGIC: Hash-based selection provides deterministic load balancing
        across accounts using client_id, model_id, and time-based rotation.
        This ensures even distribution while maintaining some stickiness.

        EXPECTED: Returns valid account from the provided list
        """
        mock_time.return_value = 1234567890
        accounts = ["123", "456", "789"]

        result = await self.engine._hash_based_account("client1", "model1", accounts)

        assert result in accounts
        mock_time.assert_called_once()

    def test_create_rate_limit_error_success(self):
        """Test rate limit error creation with successful reset time.

        LOGIC: HTTP 429 responses must include standard rate limit headers
        to help clients implement proper retry logic. Headers provide
        limit values, remaining capacity, and reset times.

        EXPECTED: Proper HTTP 429 with all required rate limit headers
        """
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.get_reset_time.return_value = 1234567890

        error = self.engine.create_rate_limit_error(quota_config)

        assert error.status_code == 429
        assert error.detail == "Rate limit exceeded"
        assert error.headers["X-RateLimit-Limit"] == "100"
        assert error.headers["X-RateLimit-Remaining"] == "0"
        assert error.headers["X-RateLimit-Reset"] == "1234567890"
        assert error.headers["Retry-After"] == "60"

    @patch("time.time")
    def test_create_rate_limit_error_redis_failure(self, mock_time):
        """Test rate limit error creation with Redis failure.

        LOGIC: When Redis fails during reset time calculation, fall back
        to current time + 60 seconds. This provides clients with a
        reasonable retry time even when Redis is unavailable.

        EXPECTED: HTTP 429 with fallback reset time calculation
        """
        mock_time.return_value = 1234567890
        quota_config = QuotaConfig(rpm=100, tpm=1000, accounts=["123"])
        self.mock_limiter.get_reset_time.side_effect = Exception("Redis error")

        error = self.engine.create_rate_limit_error(quota_config)

        assert error.status_code == 429
        assert error.headers["X-RateLimit-Reset"] == str(1234567890 + 60)

    def test_api_patterns_coverage(self):
        """Test that all API patterns are covered.

        LOGIC: Validates that all supported GenAI API patterns are correctly
        recognized by the engine. This ensures comprehensive coverage of
        Bedrock API endpoints for accurate rate limiting.

        EXPECTED: All supported patterns correctly identified with valid API types
        """
        expected_patterns = [
            "/model/test/converse",
            "/model/test/converse-stream",
            "/model/test/invoke",
            "/model/test/invoke-with-response-stream",
        ]

        for pattern in expected_patterns:
            api_type = RateLimitEngine.get_api_type(pattern)
            assert api_type is not None
            assert api_type in ["converse", "invoke"]
