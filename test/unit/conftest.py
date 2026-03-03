"""Pytest configuration and fixtures for unit tests."""

import os
import sys
from pathlib import Path

import pytest

# Disable OpenTelemetry before any imports to prevent connection attempts
os.environ["OTEL_SDK_DISABLED"] = "true"

# Add the app directory to Python path for imports
app_dir = Path(__file__).parent.parent.parent / "backend" / "app"
sys.path.insert(0, str(app_dir))


@pytest.fixture(autouse=True)
def reset_context_vars():
    """Reset context variables before each test."""
    from observability.context_vars import clear_user_context

    clear_user_context()


@pytest.fixture(autouse=True)
def mock_telemetry_setup():
    """Mock telemetry setup to prevent OTEL connection errors."""
    import os
    from unittest.mock import patch

    # Disable OTEL during tests and set safe defaults
    test_env = {
        "OTEL_SDK_DISABLED": "true",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "OTEL_SERVICE_NAME": "test-service",
        "ENVIRONMENT": "test",
    }

    with patch.dict(os.environ, test_env, clear=False):
        yield


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    from unittest.mock import Mock

    config = Mock()
    config.environment = "test"
    config.jwks_url = "https://test.com/jwks"
    config.jwt_audience = "test-audience"
    config.allowed_scopes = ["bedrockproxygateway:invoke"]
    config.valkey_cache_endpoint = "localhost"
    config.valkey_cache_port = 6379
    config.valkey_ssl = False
    config.app_hash = "test-hash"

    return config


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    from unittest.mock import Mock

    logger = Mock()
    logger.debug = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.critical = Mock()

    return logger


@pytest.fixture
def mock_telemetry():
    """Mock telemetry configuration for testing."""
    from unittest.mock import Mock

    return {
        "tracer": Mock(),
        "meter": Mock(),
        "logger": Mock(),
    }
