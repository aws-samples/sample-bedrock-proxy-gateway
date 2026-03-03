"""Unit tests for services.guardrail_service module."""

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestGuardrailService:
    """Test cases for GuardrailService class."""

    def setup_method(self):
        """Set up test fixtures."""
        import services.valkey_service

        services.valkey_service._client = None
        self.mock_ssm_client = Mock()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    def test_init(self, _mock_config, mock_ssm_class, _mock_context_logger, _mock_logger):
        """Test initialization."""
        from services.guardrail_service import GuardrailService

        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()

        assert service._ssm_client == self.mock_ssm_client
        assert service._redis is None

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_initialize_redis_failure(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test Redis initialization failure."""
        from services.guardrail_service import GuardrailService

        mock_config.valkey_url = "async+rediss://localhost:6379"
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        # Try to initialize redis and it should fail silently
        await service._ensure_redis()

        assert service._redis is None

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        self.mock_ssm_client.get_parameter_json.return_value = {
            "baseline-security": {"123": {"guardrail_id": "gr-123", "version": "1"}}
        }
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        result = await service.get_guardrail_config("baseline-security", "123")

        assert result == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "enabled",
        }

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config_not_found(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval when not found."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        self.mock_ssm_client.get_parameter_json.return_value = {}
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        result = await service.get_guardrail_config("nonexistent", "123")

        assert result is None

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config_exception(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval with exception."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        self.mock_ssm_client.get_parameter_json.side_effect = Exception("SSM error")
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        result = await service.get_guardrail_config("baseline-security", "123")

        assert result is None

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config_with_redis(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval with Redis cache."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        mock_redis = Mock()
        mock_redis.get = AsyncMock(
            return_value='{"baseline-security": {"123": {"guardrail_id": "gr-123", "version": "1"}}}'
        )
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        result = await service.get_guardrail_config("baseline-security", "123")

        assert result == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "enabled",
        }
        mock_redis.get.assert_called_once()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config_redis_miss(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval with Redis cache miss."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        mock_redis = Mock()
        mock_redis.get = AsyncMock(return_value=None)
        self.mock_ssm_client.get_parameter_json.return_value = {
            "baseline-security": {"123": {"guardrail_id": "gr-123", "version": "1"}}
        }
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        service._last_refresh = time.time()  # Skip refresh
        result = await service.get_guardrail_config("baseline-security", "123")

        assert result == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "enabled",
        }
        mock_redis.get.assert_called_once()
        self.mock_ssm_client.get_parameter_json.assert_called_once()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_guardrail_config_redis_failure(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test guardrail config retrieval with Redis failure."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        mock_redis = Mock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))
        self.mock_ssm_client.get_parameter_json.return_value = {
            "baseline-security": {"123": {"guardrail_id": "gr-123", "version": "1"}}
        }
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        service._last_refresh = time.time()  # Skip refresh
        result = await service.get_guardrail_config("baseline-security", "123")

        assert result == {
            "guardrailIdentifier": "gr-123",
            "guardrailVersion": "1",
            "trace": "enabled",
        }
        assert self.mock_ssm_client.get_parameter_json.call_count == 1

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_ensure_config_fresh_refresh_needed(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test config refresh when interval elapsed."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_redis = Mock()
        mock_redis.set = AsyncMock()
        self.mock_ssm_client.get_parameter_json.return_value = {"test": "config"}
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        service._refresh_interval = 300
        service._last_refresh = 0  # Force refresh
        await service._ensure_config_fresh()

        mock_redis.set.assert_called_once()
        self.mock_ssm_client.get_parameter_json.assert_called_once()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_ensure_config_fresh_refresh_error(
        self, mock_config, mock_ssm_class, _mock_context_logger, mock_logger
    ):
        """Test config refresh with error."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_redis = Mock()
        mock_redis.setex = AsyncMock()
        self.mock_ssm_client.get_parameter_json.side_effect = Exception("SSM error")
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        service._refresh_interval = 300
        service._last_refresh = 0  # Force refresh
        await service._ensure_config_fresh()

        mock_logger.error.assert_called_once()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_ensure_config_fresh_no_refresh(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test config refresh skipped when interval not elapsed."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        mock_redis = Mock()
        mock_redis.setex = AsyncMock()
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        service._redis = mock_redis
        service._last_refresh = time.time()
        await service._ensure_config_fresh()

        mock_redis.setex.assert_not_called()
        self.mock_ssm_client.get_parameter_json.assert_not_called()

    @patch("services.guardrail_service.logger")
    @patch("observability.context_logger.ContextLogger")
    @patch("services.guardrail_service.SSMClient")
    @patch("services.guardrail_service.config")
    @pytest.mark.asyncio
    async def test_get_available_guardrails(
        self, mock_config, mock_ssm_class, _mock_context_logger, _mock_logger
    ):
        """Test available guardrails retrieval."""
        from services.guardrail_service import GuardrailService

        mock_config.environment = "test"
        mock_config.guardrail_refresh_interval = 300
        self.mock_ssm_client.get_parameter_json.return_value = {
            "baseline-security": {"123": {"guardrail_id": "gr-123", "version": "1"}},
            "comment-analysis": {"456": {"guardrail_id": "gr-456", "version": "2"}},
        }
        mock_ssm_class.return_value = self.mock_ssm_client

        service = GuardrailService()
        result = await service.get_available_guardrails()

        assert result == ["baseline-security", "comment-analysis"]
